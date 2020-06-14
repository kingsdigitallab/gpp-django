# Generated by Django 2.2.12 on 2020-06-14 22:51

import authority.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('archival', '0094_auto_20200609_0209'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Organisation',
        ),
        migrations.AlterField(
            model_name='archivalrecord',
            name='organisations_as_subjects',
            field=models.ManyToManyField(blank=True, limit_choices_to={'entity_type__title': 'corporateBody'}, related_name='organisation_subject_for_records', to='authority.Entity', verbose_name='Corporate bodies as subjects'),
        ),
        migrations.AlterField(
            model_name='archivalrecord',
            name='persons_as_subjects',
            field=models.ManyToManyField(blank=True, limit_choices_to={'entity_type__title': 'person'}, related_name='person_subject_for_records', to='authority.Entity'),
        ),
        migrations.AlterField(
            model_name='archivalrecord',
            name='start_date',
            field=authority.fields.PartialDateField(help_text='This element is used to identify the start date of the document(s). For Collection and Series levels, year dates should be used. For Sub-Series level and below, dates should include day and month (if known). Some approximation of date should always be possible from the record-relationship to other records in the series, office holders named, external events referred to, etc. This data element is for machine-reading and should be replicated in the Date (free-text) data element. No letters, symbols or characters other than numbers should be entered.'),
        ),
        migrations.AlterField(
            model_name='collection',
            name='arrangement',
            field=models.TextField(blank=True, help_text='This element is used to provide information on the internal structure, order and/or system of classification of the unit of description. If the existing order of the papers has been preserved in cataloguing, this should be reflected in this data element. Re-arrangement of documents in the Georgian Papers is infrequent, but this data element should also be used to note any such re-arrangement or noteworthy points about the existing arrangement. At the top-level, a statement to note that &quot;this collection has been artificially created as part of the Georgian Papers digitisation and cataloguing programme&quot; should be included.'),
        ),
        migrations.AlterField(
            model_name='series',
            name='arrangement',
            field=models.TextField(blank=True, help_text='This element is used to provide information on the internal structure, order and/or system of classification of the unit of description. If the existing order of the papers has been preserved in cataloguing, this should be reflected in this data element. Re-arrangement of documents in the Georgian Papers is infrequent, but this data element should also be used to note any such re-arrangement or noteworthy points about the existing arrangement. At the top-level, a statement to note that &quot;this collection has been artificially created as part of the Georgian Papers digitisation and cataloguing programme&quot; should be included.'),
        ),
    ]
