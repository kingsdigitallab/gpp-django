# Generated by Django 2.2.12 on 2020-06-14 22:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('authority', '0089_auto_20200610_0141'),
    ]

    operations = [
        migrations.AlterField(
            model_name='biographyhistory',
            name='content',
            field=models.TextField(blank=True, verbose_name='Biography'),
        ),
        migrations.AlterField(
            model_name='biographyhistory',
            name='sources',
            field=models.TextField(blank=True, help_text='Format citations using the Chicago Style guide - http://www.chicagomanualofstyle.org/tools_citationguide/citation-guide-1.html.', verbose_name='Biography sources'),
        ),
        migrations.AlterField(
            model_name='control',
            name='language',
            field=models.ForeignKey(help_text='This element denotes the language(s) used by an entity.', on_delete=django.db.models.deletion.PROTECT, to='languages_plus.Language', verbose_name='Record language'),
        ),
        migrations.AlterField(
            model_name='control',
            name='script',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='script_codes.Script', verbose_name='Record script'),
        ),
        migrations.AlterField(
            model_name='legalstatus',
            name='term',
            field=models.CharField(blank=True, help_text='This element is used to encode information about the legal status of a corporate body. &quot;The legal status of a corporate body is typically defined and granted by authorities or through authorized agencies. Enter terms in accordance with provisions of the controlling legislation.&quot; See legal status at eac.staatsbibliothek-berlin.de.', max_length=256, verbose_name='Legal status'),
        ),
        migrations.AlterField(
            model_name='mandate',
            name='notes',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='mandate',
            name='term',
            field=models.CharField(blank=True, help_text='This element captures &quot;The source of authority or mandate for the corporate body in terms of its powers, functions, responsibilities or sphere of activities, such as a law, directive, or charter.&quot; See mandate at eac.staatsbibliothek-berlin.de.', max_length=256, verbose_name='Mandate'),
        ),
        migrations.AlterField(
            model_name='relation',
            name='relation_type',
            field=models.ForeignKey(help_text='The type of relation that the corporate body or person has to the entity being described. See https://eac.staatsbibliothek-berlin.de/ for more info.', on_delete=django.db.models.deletion.PROTECT, to='jargon.EntityRelationType', verbose_name='Relationship type'),
        ),
        migrations.AlterField(
            model_name='source',
            name='name',
            field=models.TextField(help_text='This field should contain references to the material used in creating and populating a person or corporate body record. The content of this field can include source name and ID where appropriate or full citation if required. Examples of source name and ID include - Wikipedia: George III of the United Kingdom, VIAF ID: 49264990 or Wikidata ID: Q127318.', verbose_name='Source'),
        ),
    ]
