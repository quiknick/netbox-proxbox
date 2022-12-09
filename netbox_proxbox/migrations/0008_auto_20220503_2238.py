# Generated by Django 3.2.12 on 2022-05-03 22:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_proxbox', '0007_synctask_data_instance'),
    ]

    operations = [
        migrations.AddField(
            model_name='synctask',
            name='progress',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='synctask',
            name='progress_status',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]