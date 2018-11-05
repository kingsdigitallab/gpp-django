# Generated by Django 2.0.9 on 2018-11-05 11:02

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('authority', '0005_add_dated_mixin'),
    ]

    operations = [
        migrations.AddField(
            model_name='identity',
            name='date_from',
            field=models.DateField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='identity',
            name='date_to',
            field=models.DateField(blank=True, null=True),
        ),
    ]
