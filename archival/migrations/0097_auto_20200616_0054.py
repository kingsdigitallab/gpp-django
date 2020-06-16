# Generated by Django 2.2.12 on 2020-06-15 23:54

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('archival', '0096_auto_20200615_1714'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='archivalrecord',
            name='related_materials',
        ),
        migrations.CreateModel(
            name='RelatedMaterialReference',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('context', models.CharField(blank=True, help_text='This element is used for the cross-referencing of relevant material held elsewhere in the Georgian Papers.', max_length=2048)),
                ('record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='referenced_related_materials', to='archival.ArchivalRecord')),
                ('related_record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='referencing_related_materials', to='archival.ArchivalRecord')),
            ],
        ),
    ]
