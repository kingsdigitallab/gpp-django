from django.conf import settings
from django.db import models

from controlled_vocabulary.models import ControlledTermField
from editor.signals import view_post_save
from geonames_place.models import Place as GeoPlace
from jargon.models import (
    CollaborativeWorkspaceEditorType as CWEditorType, EditingEventType,
    EntityRelationType, EntityType, Function, Gender, MaintenanceStatus,
    NamePartType, PublicationStatus, ResourceRelationType
)
from model_utils.models import TimeStampedModel
import reversion
from script_codes.models import Script

from . import constants
from .exceptions import EntityMergeException
from .fields import PartialDateField


class DateRangeMixin(models.Model):
    date_from = PartialDateField(blank=True,
                                 help_text=constants.START_DATE_HELP)
    date_to = PartialDateField(blank=True,
                               help_text=constants.END_DATE_HELP)
    display_date = models.CharField(max_length=1024, blank=True)

    class Meta:
        abstract = True

    def get_date(self):
        dates = self.__dict__

        if self.date_from:
            if self.date_to:
                return '{date_from} - {date_to}'.format(**dates)

            return '{date_from} - '.format(**dates)

        if self.date_to:
            return ' - {date_to}'.format(**dates)

        return 'Unknown'


class LanguageScriptMixin(models.Model):
    language = ControlledTermField(['iso639-2'], on_delete=models.PROTECT,
                                   help_text=constants.LANGUAGE_HELP)
    script = models.ForeignKey(Script, on_delete=models.PROTECT)

    class Meta:
        abstract = True


@reversion.register(follow=['control', 'identities'])
class Entity(TimeStampedModel, DateRangeMixin):
    entity_type = models.ForeignKey(EntityType, on_delete=models.CASCADE)
    project = models.ForeignKey(
        'archival.Project', on_delete=models.SET_NULL, blank=True, null=True,
        help_text='Which project does this record belong to?')
    not_duplicates = models.ManyToManyField('self', blank=True)

    objects = models.Manager()

    class Meta:
        verbose_name_plural = 'Entities'

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        try:
            return self.identities.order_by(
                '-preferred_identity').first().authorised_form.display_name
        except AttributeError:
            return 'Unnamed object'

    def get_all_name_entries(self):
        return NameEntry.objects.filter(identity__entity=self)

    @staticmethod
    def get_or_create_by_display_name(name, language, script, project=None):
        if not name or not language or not script:
            return None, False

        entities = Entity.objects.filter(
            identities__name_entries__display_name=name).distinct()
        if project:
            entities = entities.filter(project=project)

        if entities:
            entities_count = len(entities)
            if entities_count > 1:
                # We cannot choose between multiple entities, so
                # neither return an existing entitiy nor create a new
                # one.
                return None, False
            if entities_count == 1:
                return entities[0], False

        et, _ = EntityType.objects.get_or_create(title='person')

        entity = Entity(entity_type=et)
        if project:
            entity.project = project
        entity.save()

        identity = Identity(entity=entity)
        identity.preferred_identity = True
        identity.save()

        name_entry = NameEntry(identity=identity)
        name_entry.display_name = name
        name_entry.authorised_form = True
        name_entry.date_from = identity.date_from
        name_entry.language = language
        name_entry.script = script
        name_entry.save()

        control = Control(entity=entity)
        control.language = language
        control.script = script
        ms, _ = MaintenanceStatus.objects.get_or_create(title='new')
        ps, _ = PublicationStatus.objects.get_or_create(title='inProcess')
        control.maintenance_status = ms
        control.publication_status = ps
        control.save()

        return entity, True

    def is_deleted(self):
        return self.control.maintenance_status.title == 'deleted'

    def merge(self, entity, user=None):
        """Merges `entity` into `self`.

        This does the following:

        * Marks `entity` as deleted, with a comment mentioning the merge.

        * Creates a copy of every Identity (and recursively its
          related objects) of `entity` on `self`, setting
          preferred_identity to False on each of them.

        * Creates a copy of every Source of `entity` on `self`.

        * Creates a copy of every association of `entity` with
          ArchivalRecord objects on `self`.

        Raises an exception if the two entities are of different
        entity_types, or are associated with different projects, or
        are the same entity, or one is not an entity at all.

        """
        if not isinstance(entity, Entity):
            raise EntityMergeException(
                'An entity may only merge with another entity.')
        if self == entity:
            raise EntityMergeException('Cannot merge an entity into itself.')
        if self.project != entity.project:
            raise EntityMergeException(
                'Cannot merge entities that belong to different projects.')
        if self.entity_type != entity.entity_type:
            raise EntityMergeException(
                'Cannot merge entities that have different entity types.')
        from editor.models import RevisionMetadata
        with reversion.create_revision():
            records_to_update = self._merge(entity)
            if user is not None:
                reversion.set_user(user)
            reversion.set_comment('Merged in entity {}.'.format(entity.pk))
            event_type = EditingEventType.objects.get(title='revised')
            editor_type = CWEditorType.objects.get(title='human')
            reversion.add_meta(RevisionMetadata, editing_event_type=event_type,
                               collaborative_workspace_editor_type=editor_type)
            self.save()
        # Mark the merged entity as deleted.
        with reversion.create_revision():
            event_type = EditingEventType.objects.get(title='deleted')
            editor_type = CWEditorType.objects.get(title='human')
            reversion.add_meta(RevisionMetadata, editing_event_type=event_type,
                               collaborative_workspace_editor_type=editor_type)
            if user is not None:
                reversion.set_user(user)
            reversion.set_comment(
                'Deleted entity due to merge into entity {}.'.format(self.pk))
            control = entity.control
            control.publication_status = PublicationStatus.objects.get(
                title='inProcess')
            control.maintenance_status = MaintenanceStatus.objects.get(
                title='deleted')
            control.save()
            entity.save()
        view_post_save.send(sender=Entity, instance=self)
        view_post_save.send(sender=Entity, instance=entity)
        for record in records_to_update:
            view_post_save.send(sender=record.get_real_instance_class(),
                                instance=record)

    def _merge(self, entity):
        """Perform the data copying for a merge of `entity` into `self`."""
        for identity in entity.identities.all():
            name_entries = identity.name_entries.all()
            descriptions = identity.descriptions.all()
            relations = identity.relations.all()
            resources = identity.resources.all()
            identity.pk = None
            identity.preferred_identity = False
            identity.entity = self
            identity.save()
            for name_entry in name_entries:
                name_parts = name_entry.parts.all()
                name_entry.pk = None
                name_entry.identity = identity
                name_entry.save()
                for name_part in name_parts:
                    name_part.pk = None
                    name_part.name_entry = name_entry
                    name_part.save()
            for description in descriptions:
                try:
                    biography = description.biography_history
                except BiographyHistory.DoesNotExist:
                    biography = None
                events = description.events.all()
                functions = description.functions.all()
                languages_scripts = description.languages_scripts.all()
                legal_statuses = description.legal_statuses.all()
                local_descriptions = description.local_descriptions.all()
                mandates = description.mandates.all()
                places = description.places.all()
                description.pk = None
                description.identity = identity
                description.save()
                if biography is not None:
                    biography.pk = None
                    biography.description = description
                    biography.save()
                for event in events:
                    event.pk = None
                    event.description = description
                    event.save()
                for function in functions:
                    function.pk = None
                    function.description = description
                    function.save()
                for language_script in languages_scripts:
                    language_script.pk = None
                    language_script.description = description
                    language_script.save()
                for legal_status in legal_statuses:
                    legal_status.pk = None
                    legal_status.description = description
                    legal_status.save()
                for local_description in local_descriptions:
                    local_description.pk = None
                    local_description.description = description
                    local_description.save()
                for mandate in mandates:
                    mandate.pk = None
                    mandate.description = description
                    mandate.save()
                for place in places:
                    place.pk = None
                    place.description = description
                    place.save()
            for relation in relations:
                relation.pk = None
                relation.identity = identity
                relation.save()
            for resource in resources:
                resource.pk = None
                resource.identity = identity
                resource.save()
        control = self.control
        for source in entity.control.sources.all():
            source.pk = None
            source.control = control
            source.save()
        self.not_duplicates.remove(entity)
        records_to_update = set()
        for record in entity.person_subject_for_records.all():
            record.persons_as_subjects.add(self)
            records_to_update.add(record)
        for record in entity.related_entities.all():
            record.related_entities.add(self)
            records_to_update.add(record)
        for record in entity.organisation_subject_for_records.all():
            record.organisations_as_subjects.add(self)
            records_to_update.add(record)
        for record in entity.files_created.all():
            record.creators.add(self)
            records_to_update.add(record)
        for record in entity.files_as_relations.all():
            record.persons_as_relations.add(self)
            records_to_update.add(record)
        for record in entity.items_created.all():
            record.creators.add(self)
            records_to_update.add(record)
        for record in entity.items_as_relations.all():
            record.persons_as_relations.add(self)
            records_to_update.add(record)
        return records_to_update


@reversion.register(follow=['descriptions', 'name_entries', 'relations',
                            'resources'])
class Identity(DateRangeMixin, TimeStampedModel):
    entity = models.ForeignKey(
        Entity, on_delete=models.CASCADE, related_name='identities')

    preferred_identity = models.BooleanField()

    class Meta:
        verbose_name_plural = 'Identities'

    def __str__(self):
        try:
            return self.authorised_form.display_name
        except AttributeError:
            return 'Unsaved object'

    @property
    def authorised_form(self):
        return self.name_entries.order_by('-authorised_form').first()


@reversion.register(follow=['parts'])
class NameEntry(DateRangeMixin, LanguageScriptMixin, TimeStampedModel):
    identity = models.ForeignKey(
        Identity, on_delete=models.CASCADE, related_name='name_entries')

    display_name = models.CharField(max_length=2048)
    authorised_form = models.BooleanField()
    is_royal_name = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = 'Name entries'

    def __str__(self):
        return self.display_name or ', '.join(['{}: {}'.format(
            p.name_part_type, p.part) for p in self.parts.all()])


@reversion.register()
class NamePart(TimeStampedModel):
    name_entry = models.ForeignKey(
        NameEntry, on_delete=models.CASCADE, related_name='parts')
    name_part_type = models.ForeignKey(NamePartType, on_delete=models.PROTECT)
    part = models.CharField(max_length=256)

    def __str__(self):
        return '{}: {}'.format(self.name_part_type, self.part)


@reversion.register(follow=['biography_history', 'events', 'functions',
                            'languages_scripts', 'legal_statuses',
                            'local_descriptions', 'mandates', 'places'])
class Description(DateRangeMixin, TimeStampedModel):
    identity = models.ForeignKey(
        Identity, on_delete=models.CASCADE, related_name='descriptions')


@reversion.register()
class Place(DateRangeMixin, TimeStampedModel):
    description = models.ForeignKey(
        Description, on_delete=models.CASCADE, related_name='places')

    place = models.ForeignKey(GeoPlace, on_delete=models.CASCADE)
    address = models.TextField(blank=True)
    role = models.CharField(blank=True, max_length=256,
                            help_text=constants.PLACE_ROLE_HELP)


@reversion.register()
class LanguageScript(LanguageScriptMixin, TimeStampedModel):
    description = models.ForeignKey(Description, on_delete=models.CASCADE,
                                    related_name='languages_scripts')


@reversion.register()
class BiographyHistory(TimeStampedModel):
    description = models.OneToOneField(Description, on_delete=models.CASCADE,
                                       related_name='biography_history')

    abstract = models.TextField(help_text=constants.BIOGRAPHY_ABSTRACT_HELP)
    content = models.TextField(blank=True)
    sources = models.TextField(
        blank=True, help_text=constants.BIOGRAPHY_SOURCES_HELP)
    copyright = models.TextField(
        blank=True, help_text=constants.BIOGRAPHY_COPYRIGHT_HELP)

    class Meta:
        verbose_name = 'Biography/History'
        verbose_name_plural = 'Biography/History'


@reversion.register()
class Event(DateRangeMixin, TimeStampedModel):
    description = models.ForeignKey(
        Description, on_delete=models.CASCADE, related_name='events')

    event = models.TextField()
    place = models.ForeignKey(GeoPlace, blank=True, null=True,
                              on_delete=models.CASCADE)


@reversion.register()
class LocalDescription(DateRangeMixin, TimeStampedModel):
    description = models.ForeignKey(Description, on_delete=models.CASCADE,
                                    related_name='local_descriptions')
    gender = models.ForeignKey(Gender, help_text=constants.GENDER_HELP,
                               on_delete=models.CASCADE)
    notes = models.TextField(verbose_name='Descriptive notes', blank=True)
    citation = models.TextField(blank=True)


@reversion.register()
class Mandate(DateRangeMixin, TimeStampedModel):
    description = models.ForeignKey(Description, on_delete=models.CASCADE,
                                    related_name='mandates')

    term = models.CharField(
        max_length=256, blank=True, help_text=constants.MANDATE_HELP,
        verbose_name="Mandate")
    notes = models.TextField(blank=True)
    citation = models.TextField(blank=True)


@reversion.register()
class Function(DateRangeMixin, TimeStampedModel):
    description = models.ForeignKey(Description, on_delete=models.CASCADE,
                                    related_name='functions')
    title = models.ForeignKey(Function, verbose_name="Function",
                              on_delete=models.CASCADE)


@reversion.register()
class LegalStatus(DateRangeMixin, TimeStampedModel):
    description = models.ForeignKey(Description, on_delete=models.CASCADE,
                                    related_name='legal_statuses')

    term = models.CharField(
        max_length=256, blank=True, help_text=constants.LEGAL_STATUS_HELP,
        verbose_name="Legal status")
    notes = models.TextField(blank=True)
    citation = models.TextField(blank=True,
                                help_text=constants.LEGAL_STATUS_CITATION_HELP)

    class Meta:
        verbose_name_plural = 'Legal status'


@reversion.register()
class Relation(DateRangeMixin, TimeStampedModel):
    identity = models.ForeignKey(
        Identity, on_delete=models.CASCADE, related_name='relations')
    relation_type = models.ForeignKey(
        EntityRelationType, verbose_name="Relationship type",
        on_delete=models.PROTECT,
        help_text=constants.RELATION_TYPE_HELP)
    related_entity = models.ForeignKey(
        Entity, verbose_name="Related person or corporate body",
        on_delete=models.CASCADE, null=True,
        related_name='related_to_relations')
    relation_detail = models.TextField(
        verbose_name="Description",
        help_text=constants.RELATION_DESCRIPTION_HELP)
    place = models.ForeignKey(
        GeoPlace, verbose_name="Place related to relationship", blank=True,
        null=True, on_delete=models.CASCADE)


@reversion.register()
class Resource(TimeStampedModel):
    identity = models.ForeignKey(
        Identity, on_delete=models.CASCADE, related_name='resources')
    relation_type = models.ForeignKey(
        ResourceRelationType, verbose_name="Resource relationship type",
        on_delete=models.PROTECT,
        help_text=constants.RESOURCE_RELATIONSHIP_TYPE_HELP)
    url = models.URLField(blank=True, verbose_name="URL")
    citation = models.TextField()
    notes = models.TextField(blank=True)


@reversion.register(follow=['sources'])
class Control(TimeStampedModel):
    entity = models.OneToOneField(Entity, on_delete=models.CASCADE,
                                  related_name="control")

    maintenance_status = models.ForeignKey(
        MaintenanceStatus, on_delete=models.PROTECT)
    publication_status = models.ForeignKey(
        PublicationStatus, on_delete=models.PROTECT)

    rights_declaration = models.TextField(
        default=settings.AUTHORITY_RIGHTS_DECLARATION)
    rights_declaration_abbreviation = models.CharField(
        max_length=256, blank=True)
    rights_declaration_citation = models.URLField(
        blank=True, default=settings.AUTHORITY_RIGHTS_DECLARATION_CITATION)

    language = ControlledTermField(
        ['iso639-2'], on_delete=models.PROTECT,
        help_text=constants.LANGUAGE_HELP, verbose_name='Record language')
    script = models.ForeignKey(Script, on_delete=models.PROTECT,
                               verbose_name="Record script")

    class Meta:
        verbose_name_plural = 'Control'


@reversion.register()
class Source(TimeStampedModel):
    control = models.ForeignKey(Control, on_delete=models.CASCADE,
                                related_name="sources")
    name = models.TextField(verbose_name="Source",
                            help_text=constants.SOURCE_HELP)
    url = models.URLField(verbose_name="URL", blank=True, max_length=512)
    notes = models.TextField(blank=True)
