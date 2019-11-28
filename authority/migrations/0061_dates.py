# Generated by Django 2.1.7 on 2019-06-26 15:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authority', '0060_add_project_to_entity'),
    ]

    operations = [
        migrations.AddField(
            model_name='description',
            name='display_date',
            field=models.CharField(max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name='identity',
            name='display_date',
            field=models.CharField(max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name='legalstatus',
            name='display_date',
            field=models.CharField(max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name='localdescription',
            name='display_date',
            field=models.CharField(max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name='mandate',
            name='display_date',
            field=models.CharField(max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name='nameentry',
            name='display_date',
            field=models.CharField(max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name='place',
            name='display_date',
            field=models.CharField(max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name='relation',
            name='display_date',
            field=models.CharField(max_length=1024, null=True),
        ),
    ]
