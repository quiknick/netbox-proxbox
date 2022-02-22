import os
import pytz
import uuid
from datetime import datetime
# Provides standard field types like 'CharField' and 'ForeignKey'
from django.db import models

from django.urls import reverse

# Model class 'ChangeLoggedModel' defined by Netbox
# from extras.models import ChangeLoggedModel
from extras.models.models import ChangeLoggedModel

# Class defined by Netbox to handle IPv4/IPv6 address
# from ipam.fields import IPAddressField

# Class defined by Netbox to define (choice) the VM operational status
from netbox_proxbox.choices import TaskTypeChoices, TaskStatusChoices
from netbox_proxbox.mixin.ModelDiffMixin import ModelDiffMixin
from virtualization.models import VirtualMachineStatusChoices

# 'RestrictedQuerySet' will make it possible to filter out objects 
# for which user doest nothave specific rights
from utilities.querysets import RestrictedQuerySet
from django.dispatch import receiver
from django.db.models.signals import pre_save

TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")


# model class that subclasses 'ChangeLoggedModel'
class ProxmoxVM(ChangeLoggedModel):
    cluster = models.ForeignKey(  # Field 'cluster' links to Netbox's 'virtualization.Cluster' model
        to="virtualization.Cluster",  # and is set to 'ForeignKey' because of it.
        on_delete=models.SET_NULL,  # If Netbox linked object is deleted, set the field to NULL
        blank=True,  # Makes field optional
        null=True,  # Allows corresponding database column to be NULL (contain no value)
        verbose_name="Cluster"
    )
    node = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Node (Server)"
    )
    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.PROTECT,  # linked virtual_machine cannot be deleted as long as this object exists
        verbose_name="Proxmox VM/CT"
    )
    status = models.CharField(
        max_length=50,
        choices=VirtualMachineStatusChoices,
        default=VirtualMachineStatusChoices.STATUS_ACTIVE,
        verbose_name='Status'
    )
    proxmox_vm_id = models.PositiveIntegerField(verbose_name="Proxmox VM ID")

    vcpus = models.PositiveIntegerField(verbose_name="VCPUs")

    memory = models.PositiveIntegerField(verbose_name="Memory (MB)")
    disk = models.PositiveIntegerField(verbose_name="Disk (GB)")
    type = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Type (qemu or lxc)"
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Description"
    )

    # Retrieve and filter 'ProxmoxVM' records
    objects = RestrictedQuerySet.as_manager()

    # display name of ProxmoxVM object defined to virtual_machine
    def __str__(self):
        return f"{self.virtual_machine}"

    def get_absolute_url(self):
        """Provide absolute URL to a ProxmoxVM object."""

        # 'reverse' generate correct URL for given class record based on the provided pk.
        return reverse("plugins:netbox_proxbox:proxmoxvm", kwargs={"pk": self.pk})

    """
    def validate_unique(self, exclude=None):
        # Check for a duplicate name on a VM assigned to the same Cluster and no Tenant. This is necessary
        # because Django does not consider two NULL fields to be equal, and thus will not trigger a violation
        # of the uniqueness constraint without manual intervention.
        if self.virtual_machine is None and VirtualMachine.objects.exclude(pk=self.pk).filter(
                name=self.virtual_machine, cluster=self.cluster, tenant__isnull=True
        ):
            raise ValidationError({
                'name': 'A virtual machine with this name already exists in the assigned cluster.'
            })

        super().validate_unique(exclude)
    """


class SyncTask(ModelDiffMixin, ChangeLoggedModel):
    task_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    job_id = models.CharField(max_length=255, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    task_type = models.CharField(max_length=255, choices=TaskTypeChoices, default=TaskTypeChoices.UNDEFINED)
    status = models.CharField(max_length=255, choices=TaskStatusChoices, default=TaskStatusChoices.STATUS_UNKNOWN)
    message = models.CharField(max_length=512, blank=True, null=True)
    fail_reason = models.CharField(max_length=512, blank=True, null=True)
    done = models.BooleanField(default=False)
    remove_unused = models.BooleanField(default=True)
    scheduled_time = models.DateTimeField(blank=True)
    start_time = models.DateTimeField(null=True)
    end_time = models.DateTimeField(null=True)
    duration = models.PositiveIntegerField(blank=True, null=True)
    log = models.TextField(blank=True)
    user = models.CharField(max_length=255, blank=True)
    domain = models.CharField(max_length=255, blank=True, null=True)
    parent = models.ForeignKey(
        to='self',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    device = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="Node")
    cluster = models.ForeignKey(  # Field 'cluster' links to Netbox's 'virtualization.Cluster' model
        to="virtualization.Cluster",  # and is set to 'ForeignKey' because of it.
        on_delete=models.SET_NULL,  # If Netbox linked object is deleted, set the field to NULL
        blank=True,  # Makes field optional
        null=True,  # Allows corresponding database column to be NULL (contain no value)
        verbose_name="Cluster"
    )
    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.SET_NULL,  # linked virtual_machine cannot be deleted as long as this object exists
        blank=True,
        null=True,
        verbose_name="Proxmox VM/CT"
    )
    # Retrieve and filter 'ProxmoxVM' records
    objects = RestrictedQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if 'message' in self.diff or self._state.adding:
            if self.log is None or self.log == '':
                self.log = self.message + '\n'
            else:
                self.log += self.message + '\n'
        super(SyncTask, self).save(*args, **kwargs)
