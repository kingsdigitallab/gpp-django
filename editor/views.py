from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import User
from django.core import serializers
from django.forms import modelformset_factory
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from haystack.generic_views import FacetedSearchView, SearchView
from haystack.query import SearchQuerySet

from controlled_vocabulary.utils import search_term_or_none
from script_codes.models import Script

import reversion
from reversion.models import Revision, Version
from reversion.views import create_revision

from archival.models import (
    ArchivalRecord, ArchivalRecordTranscription, Collection, File, Item,
    Series)
from authority.models import Control, Entity
from jargon.models import (
    CollaborativeWorkspaceEditorType as CWEditorType, EditingEventType,
    MaintenanceStatus, PublicationStatus)

from .forms import (
    ArchivalRecordFacetedSearchForm, BaseUserFormset, EditorProfileForm,
    EntityCreateForm, EntityEditForm, EntityFacetedSearchForm,
    DeletedFacetedSearchForm, LogForm, PasswordChangeForm, SearchForm,
    UserCreateForm, UserEditForm, UserForm, assemble_form_errors,
    get_archival_record_edit_form_for_subclass,
)
from .models import EditorProfile, RevisionMetadata
from .signals import view_post_save


def can_show_delete_page(profile_role):
    return profile_role in (EditorProfile.ADMIN, EditorProfile.MODERATOR)


def is_user_admin(user):
    try:
        return user.editor_profile.role == EditorProfile.ADMIN
    except AttributeError:
        return False


def is_user_editor_plus(user):
    try:
        return user.editor_profile.role in (
            EditorProfile.ADMIN, EditorProfile.MODERATOR, EditorProfile.EDITOR)
    except AttributeError:
        return False


def is_user_moderator_plus(user):
    try:
        return user.editor_profile.role in (
            EditorProfile.ADMIN, EditorProfile.MODERATOR)
    except AttributeError:
        return False


class FacetMixin:

    def _create_apply_link(self, value_data, query_dict, facet):
        """Return a link to apply the facet value in `value_data` and False to
        indicate that the facet is not selected."""
        qd = query_dict.copy()
        value = value_data[0]
        facets = qd.getlist('selected_facets')
        new_facet = '{}_exact:{}'.format(facet, value)
        qd.setlist('selected_facets', facets + [new_facet])
        link = '?{}'.format(qd.urlencode())
        return link, False

    def _create_unapply_link(self, value_data, query_dict, facet):
        """Return a link to unapply the facet value in `value_data` and True
        to indicate that the facet is selected."""
        qd = query_dict.copy()
        value = value_data[0]
        facets = qd.getlist('selected_facets')
        old_facet = '{}_exact:{}'.format(facet, value)
        facets.remove(old_facet)
        qd.setlist('selected_facets', facets)
        link = qd.urlencode()
        if link:
            link = '?{}'.format(link)
        else:
            link = '.'
        return link, True

    def _merge_facets(self, facets, query_dict):
        """Return the Haystack `facets` annotated with links to apply or
        unapply the facet values. Data from `query_dict` is used to
        determine selected facets."""
        selected_facets = self._split_selected_facets(
            query_dict.getlist('selected_facets'))
        selected = []
        if not facets.get('fields'):
            return facets
        for facet, values in facets['fields'].items():
            # Some facet field values are a model object ID, so get
            # a display string for them.
            display_values = None
            if facet in ('addressees', 'related_entities', 'writers'):
                display_values = Entity.objects.filter(
                    id__in=[value[0] for value in values])
            new_values = []
            for value_data in values:
                obj_id, obj_count = value_data
                if obj_id in selected_facets.get(facet, []):
                    link, is_selected = self._create_unapply_link(
                        value_data, query_dict, facet)
                else:
                    link, is_selected = self._create_apply_link(
                        value_data, query_dict, facet)
                if display_values is None:
                    new_value = (obj_id, obj_count, link, is_selected)
                else:
                    new_value = (str(display_values.get(id=obj_id)), obj_count,
                                 link, is_selected)
                new_values.append(new_value)
                if obj_id in selected_facets.get(facet, []):
                    selected.append(new_value)
            facets['fields'][facet] = new_values
            facets['selected'] = selected
        return facets

    def _split_selected_facets(self, selected_facets):
        """Return a dictionary of selected facet values keyed by the facet
        each belongs to."""
        split_facets = {}
        for selected_facet in selected_facets:
            facet, value = selected_facet.split(':', maxsplit=1)
            facet = facet[:-len('_exact')]
            split_facets.setdefault(facet, []).append(value)
        return split_facets


class HomeView(UserPassesTestMixin, SearchView):

    template_name = 'editor/home.html'
    queryset = SearchQuerySet().models(
        Collection, Entity, File, Item, Series).exclude(
            maintenance_status='deleted')
    form_class = SearchForm

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['current_section'] = 'home'
        user = self.request.user
        entities, records = self._get_recently_modified(user)
        context['recently_modified_entities'] = entities
        context['recently_modified_records'] = records
        entities, records = self._get_unpublished_records(user)
        context['unpublished_entities'] = entities
        context['unpublished_records'] = records
        context['show_delete'] = can_show_delete_page(user.editor_profile.role)
        return context

    def _get_ids_from_version_for_user(self, model, user):
        versions = Version.objects.get_for_model(model).filter(
            revision__user=user)
        return [version.object_id for version in versions]

    def _get_recently_modified(self, user):
        """Return the archival records and entities most recently modified by
        `user`."""
        entity_ids = self._get_ids_from_version_for_user(Entity, user)
        entities = Entity.objects.filter(id__in=entity_ids)
        collection_ids = self._get_ids_from_version_for_user(Collection, user)
        file_ids = self._get_ids_from_version_for_user(File, user)
        item_ids = self._get_ids_from_version_for_user(Item, user)
        series_ids = self._get_ids_from_version_for_user(Series, user)
        record_ids = collection_ids + file_ids + item_ids + series_ids
        records = ArchivalRecord.objects.filter(id__in=record_ids)
        return entities, records

    def _get_unpublished_records(self, user):
        entities = None
        records = None
        if user.editor_profile.role in (EditorProfile.ADMIN,
                                        EditorProfile.MODERATOR):
            entities = Entity.objects.exclude(
                control__publication_status__title='published').exclude(
                    control__maintenance_status__title='deleted')
            records = ArchivalRecord.objects.exclude(
                publication_status__title='published').exclude(
                    maintenance_status__title='deleted')
        return entities, records

    def test_func(self):
        return is_user_editor_plus(self.request.user)


class EntityListView(UserPassesTestMixin, FacetedSearchView, FacetMixin):

    template_name = 'editor/entities_list.html'
    queryset = SearchQuerySet().models(Entity).exclude(
        maintenance_status='deleted').facet('entity_type').facet(
            'related_entities', size=0)
    form_class = EntityFacetedSearchForm
    facet_fields = []

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['current_section'] = 'entities'
        context['facets'] = self._merge_facets(context['facets'],
                                               self.request.GET.copy())
        context['show_delete'] = can_show_delete_page(
            self.request.user.editor_profile.role)
        return context

    def test_func(self):
        return is_user_editor_plus(self.request.user)


class DeletedListView(UserPassesTestMixin, FacetedSearchView, FacetMixin):

    template_name = 'editor/deleted_list.html'
    form_class = DeletedFacetedSearchForm
    queryset = SearchQuerySet().models(
        Collection, Entity, File, Item, Series).filter(
            maintenance_status='deleted').facet('addressees', size=0).facet(
                'archival_level').facet('entity_type').facet(
                    'languages', size=0).facet('writers', size=0)
    facet_fields = []

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['current_section'] = 'deleted'
        context['facets'] = self._merge_facets(context['facets'],
                                               self.request.GET.copy())
        context['show_delete'] = can_show_delete_page(
            self.request.user.editor_profile.role)
        return context

    def test_func(self):
        return is_user_moderator_plus(self.request.user)


class RecordListView(UserPassesTestMixin, FacetedSearchView, FacetMixin):

    template_name = 'editor/records_list.html'
    queryset = SearchQuerySet().models(Collection, File, Item, Series).exclude(
        maintenance_status='deleted').facet('addressees', size=0).facet(
            'archival_level').facet('languages', size=0).facet(
                'writers', size=0)
    form_class = ArchivalRecordFacetedSearchForm
    facet_fields = []

    def _create_unapply_year_link(self, query_dict):
        """Return a link to unapply the start and end year 'facet'."""
        qd = query_dict.copy()
        if 'start_year' in qd:
            del qd['start_year']
        if 'end_year' in qd:
            del qd['end_year']
        link = qd.urlencode()
        if link:
            link = '?{}'.format(link)
        else:
            link = '.'
        return link

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['current_section'] = 'records'
        context['end_year'] = self.request.GET.get('end_year')
        context['facets'] = self._merge_facets(context['facets'],
                                               self.request.GET.copy())
        context['max_year'] = context['form']._max_year
        context['min_year'] = context['form']._min_year
        context['start_year'] = self.request.GET.get('start_year')
        context['writer_manager'] = Entity.objects
        context['year_remove_link'] = self._create_unapply_year_link(
            self.request.GET)
        context['show_delete'] = can_show_delete_page(
            self.request.user.editor_profile.role)
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # By making start_date and end_date into a pseudo-facet, we
        # have put ourselves in a bind. It is bad UI to restrict the
        # date range to the values that fall within the existing
        # queryset (which might be bound by a previously specified
        # date range), because that would require removing the date
        # facet entirely before being able to specify a new date range
        # that extended beyond the current one.
        #
        # On the other hand, not restricting the date range to the
        # values that fall within the existing queryset means that it
        # may be possible to select a date range that will have no
        # results within it, if there are other facet values selected.
        #
        # To avoid both problems, we could make a second query that
        # uses all specified facets except for the date, and get the
        # possible date range from that, but now we're making multiple
        # search queries in order to do a single search. No, we won't
        # do that.
        #
        # Here we go with option #2, having the date range be the full
        # span of dates across all records, not just those in the
        # search results.
        start_dates = ArchivalRecord.objects.exclude(
            start_date='').values_list('start_date', flat=True)
        if len(start_dates) == 0:
            kwargs.update({'max_year': None, 'min_year': None})
            return kwargs
        min_year = sorted(start_dates, key=lambda x: x[:4])[0][:4]
        end_dates = ArchivalRecord.objects.exclude(end_date='').values_list(
            'end_date', flat=True)
        if not end_dates:
            end_dates = start_dates
        max_year = sorted(end_dates, key=lambda x: x[:4], reverse=True)[0][:4]
        kwargs.update({'max_year': max_year, 'min_year': min_year})
        return kwargs

    def test_func(self):
        return is_user_editor_plus(self.request.user)


@user_passes_test(is_user_editor_plus)
def account_control(request):
    user = request.user
    AllUsersFormSet = modelformset_factory(
        User, extra=0, can_delete=True, form=UserForm, formset=BaseUserFormset)
    user_form = UserEditForm(instance=user)
    password_form = PasswordChangeForm(user=user)
    all_users_formset = None
    saved_user = request.GET.get('saved_user', False)
    saved_password = request.GET.get('saved_password', False)
    saved_all_users = request.GET.get('saved_all_users', False)
    if user.editor_profile.role == EditorProfile.ADMIN:
        all_users_formset = AllUsersFormSet()
    if request.method == 'POST':
        redirect_url = reverse('editor:account-control')
        if request.POST.get('user_submit') is not None:
            user_form = UserEditForm(request.POST, instance=user)
            if user_form.is_valid():
                user_form.save()
                return redirect(redirect_url + '?saved_user=true')
        elif request.POST.get('password_submit') is not None:
            password_form = PasswordChangeForm(data=request.POST, user=user)
            if password_form.is_valid():
                password_form.save()
                return redirect(redirect_url + '?saved_password=true')
        elif (user.editor_profile.role == EditorProfile.ADMIN and
              request.POST.get('all_users_submit') is not None):
            # Changing editor profile role or deleting user.
            all_users_formset = AllUsersFormSet(request.POST)
            if all_users_formset.is_valid():
                all_users_formset.save()
                return redirect(redirect_url + '?saved_all_users=true')
    context = {
        'all_users_formset': all_users_formset,
        'current_section': 'account',
        'password_form': password_form,
        'saved_all_users': saved_all_users,
        'saved_password': saved_password,
        'saved_user': saved_user,
        'show_delete': can_show_delete_page(user.editor_profile.role),
        'user': user,
        'user_form': user_form,
    }
    return render(request, 'editor/account_control.html', context)


@user_passes_test(is_user_editor_plus)
@create_revision()
def entity_create(request):
    if request.method == 'POST':
        form = EntityCreateForm(request.POST)
        if form.is_valid():
            reversion.set_comment('Created empty entity.')
            event_type = EditingEventType.objects.get(title='created')
            editor_type = CWEditorType.objects.get(title='human')
            reversion.add_meta(RevisionMetadata, editing_event_type=event_type,
                               collaborative_workspace_editor_type=editor_type)
            entity = Entity()
            entity.entity_type = form.cleaned_data['entity_type']
            entity.save()
            language = search_term_or_none('iso639-2', 'eng', exact=True)
            script = Script.objects.get(name='Latin')
            ms = MaintenanceStatus.objects.get(title='new')
            ps = PublicationStatus.objects.get(title='inProcess')
            control = Control(entity=entity, language=language, script=script,
                              maintenance_status=ms, publication_status=ps)
            control.save()
            view_post_save.send(sender=Entity, instance=entity)
            return redirect('editor:entity-edit', entity_id=entity.pk)
    else:
        form = EntityCreateForm()
    context = {
        'current_section': 'entities',
        'form': form,
        'show_delete': can_show_delete_page(request.user.editor_profile.role),
    }
    return render(request, 'editor/entity_create.html', context)


@require_POST
@user_passes_test(is_user_editor_plus)
@create_revision()
def entity_delete(request, entity_id):
    entity = get_object_or_404(Entity, pk=entity_id)
    # Can't delete a deleted record.
    if entity.is_deleted():
        return redirect('editor:entity-history', entity_id=entity_id)
    # Editors may only delete inProcess entities.
    if entity.control.publication_status.title != 'inProcess' and \
       request.user.editor_profile.role == EditorProfile.EDITOR:
        return HttpResponseForbidden()
    if request.POST.get('DELETE') == 'DELETE':
        reversion.set_comment('Deleted entity.')
        event_type = EditingEventType.objects.get(title='deleted')
        editor_type = CWEditorType.objects.get(title='human')
        reversion.add_meta(RevisionMetadata, editing_event_type=event_type,
                           collaborative_workspace_editor_type=editor_type)
        control = entity.control
        control.publication_status = PublicationStatus.objects.get(
            title='inProcess')
        control.maintenance_status = MaintenanceStatus.objects.get(
            title='deleted')
        control.save()
        entity.save()
        view_post_save.send(sender=Entity, instance=entity)
        return redirect('editor:entities-list')
    return redirect('editor:entity-edit', entity_id=entity_id)


@user_passes_test(is_user_editor_plus)
@create_revision()
def entity_edit(request, entity_id):
    entity = get_object_or_404(Entity, pk=entity_id)
    editor_role = request.user.editor_profile.role
    # For the simplified editing workflow, Editors can edit objects
    # regardless of their publication or maintenance status.
    #
    # if entity.is_deleted() and editor_role == EditorProfile.EDITOR:
    #     return redirect('editor:entity-history', entity_id=entity_id)
    # if entity.control.publication_status.title != 'inProcess' and \
    #    editor_role == EditorProfile.EDITOR:
    #     return HttpResponseForbidden()
    reverted = request.GET.get('reverted', False)
    saved = request.GET.get('saved', False)
    form_errors = []
    current_section = 'entities'
    is_deleted = False
    is_corporate_body = entity.entity_type.title == 'corporateBody'
    if entity.control.maintenance_status == MaintenanceStatus.objects.get(
            title='deleted'):
        is_deleted = True
        current_section = 'deleted'
    if request.method == 'POST':
        form = EntityEditForm(request.POST, editor_role=editor_role,
                              instance=entity)
        log_form = LogForm(request.POST)
        if form.is_valid() and log_form.is_valid():
            entity.control.maintenance_status = MaintenanceStatus.objects.get(
                title='revised')
            entity.control.save()
            reversion.set_comment(log_form.cleaned_data['comment'])
            event_type = EditingEventType.objects.get(title='revised')
            editor_type = CWEditorType.objects.get(title='human')
            reversion.add_meta(RevisionMetadata, editing_event_type=event_type,
                               collaborative_workspace_editor_type=editor_type)
            form.save()
            view_post_save.send(sender=Entity, instance=entity)
            url = reverse('editor:entity-edit',
                          kwargs={'entity_id': entity_id}) + '?saved=true'
            return redirect(url)
        else:
            form_errors = assemble_form_errors(form)
    else:
        form = EntityEditForm(editor_role=editor_role, instance=entity)
        log_form = LogForm()
    context = {
        'current_section': current_section,
        'delete_url': reverse('editor:entity-delete',
                              kwargs={'entity_id': entity_id}),
        'entity': entity,
        'form_errors': form_errors,
        'form': form,
        'form_media': form.media,
        'is_deleted': is_deleted,
        'is_corporate_body': is_corporate_body,
        'last_revision': Version.objects.get_for_object(entity)[0].revision,
        'log_form': log_form,
        'reverted': reverted,
        'saved': saved,
        'show_delete': can_show_delete_page(editor_role),
    }
    return render(request, 'editor/entity_edit.html', context)


@user_passes_test(is_user_editor_plus)
def entity_history(request, entity_id):
    entity = get_object_or_404(Entity, pk=entity_id)
    control = entity.control
    context = {
        'current_section': 'entities',
        'edit_url': reverse('editor:entity-edit',
                            kwargs={'entity_id': entity_id}),
        'item': entity,
        'maintenance_status': control.maintenance_status,
        'publication_status': control.publication_status,
        'show_delete': can_show_delete_page(request.user.editor_profile.role),
        'versions': Version.objects.get_for_object(entity),
    }
    return render(request, 'editor/history.html', context)


@user_passes_test(is_user_editor_plus)
def entity_related(request, entity_id):
    entity = get_object_or_404(Entity, pk=entity_id)
    context = {
        'addressees': entity.files_as_relations.all(),
        'corporate_body_subjects':
        entity.organisation_subject_for_records.all(),
        'current_section': 'entities',
        'edit_url': reverse('editor:entity-edit',
                            kwargs={'entity_id': entity_id}),
        'item': entity,
        'object_type': 'entity',
        'show_delete': can_show_delete_page(request.user.editor_profile.role),
        'person_subjects': entity.person_subject_for_records.all(),
        'writers': entity.files_created.all(),
    }
    return render(request, 'editor/related.html', context)


@user_passes_test(is_user_editor_plus)
def entity_duplicates(request, entity_id):
    entity = get_object_or_404(Entity, pk=entity_id)
    control = entity.control
    context = {
        'current_section': 'entities',
        'edit_url': reverse('editor:entity-edit',
                            kwargs={'entity_id': entity_id}),
        'entity_id': entity_id,
        'maintenance_status': control.maintenance_status,
        'publication_status': control.publication_status,
        'entity': entity,
        'show_delete': can_show_delete_page(request.user.editor_profile.role),
        'last_revision': Version.objects.get_for_object(entity)[0].revision,
    }
    return render(request, 'editor/duplicates.html', context)


@user_passes_test(is_user_admin)
@create_revision()
@require_POST
def record_delete(request, record_id):
    record = get_object_or_404(ArchivalRecord, pk=record_id)
    # Can't delete a deleted record.
    if record.is_deleted():
        return redirect('editor:record-history', record_id=record_id)
    # Editors may only delete inProcess records.
    if record.publication_status.title != 'inProcess' and \
       request.user.editor_profile.role == EditorProfile.EDITOR:
        raise HttpResponseForbidden()
    if request.POST.get('DELETE') == 'DELETE':
        reversion.set_comment('Deleted archival record.')
        event_type = EditingEventType.objects.get(title='deleted')
        editor_type = CWEditorType.objects.get(title='human')
        reversion.add_meta(RevisionMetadata, editing_event_type=event_type,
                           collaborative_workspace_editor_type=editor_type)
        record.publication_status = PublicationStatus.objects.get(
            title='inProcess')
        record.maintenance_status = MaintenanceStatus.objects.get(
            title='deleted')
        record.save()
        view_post_save.send(sender=record.get_real_instance_class(),
                            instance=record)
        return redirect('editor:records-list')
    return redirect('editor:record-edit', record_id=record_id)


@user_passes_test(is_user_editor_plus)
@create_revision()
def record_edit(request, record_id):
    record = get_object_or_404(ArchivalRecord, pk=record_id)
    editor_role = request.user.editor_profile.role
    is_admin = editor_role == EditorProfile.ADMIN
    # For the simplified editing workflow, Editors can edit objects
    # regardless of their publication or maintenance status.
    #
    # if record.is_deleted() and editor_role == EditorProfile.EDITOR:
    #     return redirect('editor:record-history', record_id=record_id)
    # if record.publication_status.title != 'inProcess' and \
    #    editor_role == EditorProfile.EDITOR:
    #     return HttpResponseForbidden()
    reverted = request.GET.get('reverted', False)
    saved = request.GET.get('saved', False)
    current_section = 'records'
    is_deleted = False
    ra_references = record.references.filter(source__title='RA').values_list(
        'unitid', flat=True)
    if record.maintenance_status == MaintenanceStatus.objects.get(
            title='deleted'):
        current_section = 'deleted'
        is_deleted = True
    form_class = get_archival_record_edit_form_for_subclass(record)
    if request.method == 'POST':
        form = form_class(request.POST, editor_role=editor_role,
                          instance=record)
        log_form = LogForm(request.POST)
        if form.is_valid() and log_form.is_valid():
            record.maintenance_status = MaintenanceStatus.objects.get(
                title='revised')
            reversion.set_comment(log_form.cleaned_data['comment'])
            event_type = EditingEventType.objects.get(title='revised')
            editor_type = CWEditorType.objects.get(title='human')
            reversion.add_meta(RevisionMetadata, editing_event_type=event_type,
                               collaborative_workspace_editor_type=editor_type)
            form.save()
            view_post_save.send(sender=record.get_real_instance_class(),
                                instance=record)
            url = reverse('editor:record-edit',
                          kwargs={'record_id': record_id}) + '?saved=true'
            return redirect(url)
    else:
        form = form_class(editor_role=editor_role, instance=record)
        log_form = LogForm()
    context = {
        'current_section': current_section,
        'delete_url': reverse('editor:record-delete',
                              kwargs={'record_id': record_id}),
        'form': form,
        'form_media': form.media,
        'images': record.transcription_images.all(),
        'is_admin': is_admin,
        'is_deleted': is_deleted,
        'last_revision': Version.objects.get_for_object(record)[0].revision,
        'log_form': log_form,
        'ra_references': ra_references,
        'record': record,
        'reverted': reverted,
        'saved': saved,
        'show_delete': can_show_delete_page(editor_role),
    }
    return render(request, 'editor/record_edit.html', context)


@user_passes_test(is_user_editor_plus)
def record_history(request, record_id):
    record = get_object_or_404(ArchivalRecord, pk=record_id)
    context = {
        'current_section': 'records',
        'edit_url': reverse('editor:record-edit',
                            kwargs={'record_id': record_id}),
        'item': record,
        'maintenance_status': record.maintenance_status,
        'publication_status': record.publication_status,
        'show_delete': can_show_delete_page(request.user.editor_profile.role),
        'versions': Version.objects.get_for_object(record),
    }
    return render(request, 'editor/history.html', context)


@user_passes_test(is_user_editor_plus)
def record_hierarchy(request, record_id):
    record = get_object_or_404(ArchivalRecord, pk=record_id)
    context = {
        'current_section': 'records',
        'edit_url': reverse('editor:record-edit',
                            kwargs={'record_id': record_id}),
        'item': record,
        'show_delete': can_show_delete_page(request.user.editor_profile.role)
    }
    return render(request, 'editor/hierarchy.html', context)


@user_passes_test(is_user_editor_plus)
def record_related(request, record_id):
    record = get_object_or_404(ArchivalRecord, pk=record_id)
    addressees = []
    writers = []
    if record.organisations_as_subjects.all():
        addressees = record.organisations_as_subjects.all()
    if record.organisations_as_subjects.all():
        writers = record.creators.all()
    context = {
        'addressees': addressees,
        'corporate_body_subjects': record.organisations_as_subjects.all(),
        'current_section': 'records',
        'edit_url': reverse('editor:record-edit',
                            kwargs={'record_id': record_id}),
        'item': record,
        'object_type': 'record',
        'person_subjects': record.persons_as_subjects.all(),
        'show_delete': can_show_delete_page(request.user.editor_profile.role),
        'writers': writers,
    }
    return render(request, 'editor/related.html', context)


@user_passes_test(is_user_editor_plus)
def accessibility_statement(request):
    context = {
        'show_delete': can_show_delete_page(request.user.editor_profile.role)
    }
    return render(request, 'editor/accessibility_statement.html', context)


@user_passes_test(is_user_editor_plus)
def record_transcriptions(request, record_id):
    record = get_object_or_404(ArchivalRecord, pk=record_id)
    queryset = ArchivalRecordTranscription.objects.filter(
        record=record)
    data = serializers.serialize('json', queryset,
                                 fields=('order', 'transcription'))
    return HttpResponse(data, content_type='application/json')


@user_passes_test(is_user_editor_plus)
@require_POST
def revert(request):
    revision_id = request.POST.get('revision_id')
    revision = get_object_or_404(Revision, pk=revision_id)
    revision.revert(delete=True)
    for version in revision.version_set.all():
        model = version.content_type.model_class()
        obj = model.objects.get(pk=version.object_id)
        view_post_save.send(sender=model, instance=obj)
    return redirect(request.POST.get('redirect_url')
                    + '?reverted={}'.format(revision_id))


@user_passes_test(is_user_admin)
def user_create(request):
    editor_role = request.user.editor_profile.role
    if request.method == 'POST':
        user_form = UserCreateForm(request.POST)
        profile_form = EditorProfileForm(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            # EditorProfile is created automatically via signal.
            role = profile_form.cleaned_data['role']
            user.editor_profile.role = role
            user.editor_profile.save()
            return redirect('editor:account-control')
    else:
        user_form = UserCreateForm()
        profile_form = EditorProfileForm()
    context = {
        'profile_form': profile_form,
        'show_delete': can_show_delete_page(editor_role),
        'user_form': user_form,
    }
    return render(request, 'editor/user_create.html', context)
