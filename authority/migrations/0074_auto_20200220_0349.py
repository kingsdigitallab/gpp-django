# Generated by Django 2.2.5 on 2020-02-20 03:49

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('authority', '0073_auto_20200114_0831'),
    ]

    operations = [
        migrations.AddField(
            model_name='control',
            name='rights_declaration_abbreviation',
            field=models.CharField(blank=True, max_length=256),
        ),
        migrations.AddField(
            model_name='control',
            name='rights_declaration_citation',
            field=models.URLField(blank=True),
        ),
        migrations.AlterField(
            model_name='control',
            name='language',
            field=models.ForeignKey(help_text='This element denotes the language(s) used by an entity.', on_delete=django.db.models.deletion.PROTECT, to='languages_plus.Language'),
        ),
        migrations.AlterField(
            model_name='control',
            name='script',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='script_codes.Script'),
        ),
        migrations.AlterField(
            model_name='languagescript',
            name='language',
            field=models.ForeignKey(help_text='This element denotes the language(s) used by an entity.', on_delete=django.db.models.deletion.PROTECT, to='languages_plus.Language'),
        ),
        migrations.AlterField(
            model_name='languagescript',
            name='script',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='script_codes.Script'),
        ),
        migrations.AlterField(
            model_name='nameentry',
            name='language',
            field=models.ForeignKey(help_text='This element denotes the language(s) used by an entity.', on_delete=django.db.models.deletion.PROTECT, to='languages_plus.Language'),
        ),
        migrations.AlterField(
            model_name='nameentry',
            name='script',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='script_codes.Script'),
        ),
    ]
