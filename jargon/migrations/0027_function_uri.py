# Generated by Django 2.2.12 on 2020-06-18 23:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jargon', '0026_auto_20200422_0340'),
    ]

    operations = [
        migrations.AddField(
            model_name='function',
            name='uri',
            field=models.URLField(blank=True),
        ),
    ]
