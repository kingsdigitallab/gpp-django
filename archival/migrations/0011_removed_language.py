# Generated by Django 2.0.9 on 2018-10-10 15:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('archival', '0010_dummy_fields_for_autocomplete_models'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='collection',
            name='languages',
        ),
        migrations.RemoveField(
            model_name='file',
            name='languages',
        ),
        migrations.RemoveField(
            model_name='item',
            name='languages',
        ),
        migrations.RemoveField(
            model_name='series',
            name='languages',
        ),
        migrations.DeleteModel(
            name='Language',
        ),
    ]
