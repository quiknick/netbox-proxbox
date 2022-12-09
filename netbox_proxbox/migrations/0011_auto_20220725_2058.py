# Generated by Django 3.2.12 on 2022-07-25 20:58

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('virtualization', '0026_vminterface_bridge'),
        ('dcim', '0144_fix_cable_abs_length'),
        ('netbox_proxbox', '0010_auto_20220722_1502'),
    ]

    operations = [
        migrations.AddField(
            model_name='proxmoxvm',
            name='config_data',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='proxmoxvm',
            name='device',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dcim.device'),
        ),
        migrations.AddField(
            model_name='proxmoxvm',
            name='instance_data',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='proxmoxvm',
            name='name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='proxmoxvm',
            name='cluster',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='virtualization.cluster'),
        ),
        migrations.AlterField(
            model_name='proxmoxvm',
            name='virtual_machine',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='virtualization.virtualmachine'),
        ),
        migrations.AlterField(
            model_name='synctask',
            name='cluster',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='virtualization.cluster'),
        ),
        migrations.AlterField(
            model_name='synctask',
            name='device',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dcim.device'),
        ),
        migrations.AlterField(
            model_name='synctask',
            name='end_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='synctask',
            name='log',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='synctask',
            name='scheduled_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='synctask',
            name='start_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='synctask',
            name='user',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='synctask',
            name='virtual_machine',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='virtualization.virtualmachine'),
        ),
    ]
