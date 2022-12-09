import pytz
from datetime import datetime
from .util_functions import nb_search_data_, get_session
from .virtualmachine import get_set_vm
from ..models import ProxmoxVM


def get_resources(proxmox_vm):
    # Save values from Proxmox
    vcpus = float(proxmox_vm["maxcpu"])

    # Convert bytes to megabytes and then convert float to integer
    memory_Mb = proxmox_vm["maxmem"]
    memory_Mb = int(memory_Mb / 1048576)

    # Convert bytes to gigabytes and then convert float to integer
    disk_Gb = proxmox_vm["maxdisk"]
    disk_Gb = int(disk_Gb / 1000000000)

    return vcpus, memory_Mb, disk_Gb


def set_get_proxbox_item(vm_info_task, cluster=None):
    # print('[OK] STARTING PROCESS FOR PROXBOX')
    proxmox_json = vm_info_task.data_instance
    domain = vm_info_task.domain
    cluster, vmid, node, proxmox_vm_name, proxmox_session, proxmox = nb_search_data_(proxmox_json, vm_info_task.domain,
                                                                                     cluster)

    return set_get_proxbox_item_basic(proxmox_vm_name, domain, proxmox_json, node, vmid, vm_info_task.job_id, cluster)


def set_get_proxbox_item_basic(proxmox_vm_name, domain, proxmox_json, node, vmid, job_id, cluster):
    proxmox_session = get_session(domain)
    port = proxmox_session.get("PROXMOX_PORT", "8006")
    proxmox = proxmox_session.get('PROXMOX_SESSION')

    config = None
    vm_type = proxmox_json['type']
    try:
        if vm_type == 'qemu':
            config = proxmox.nodes(node).qemu(vmid).config.get()
        if vm_type == 'lxc':
            config = proxmox.nodes(node).lxc(vmid).config.get()
    except Exception as e:
        print("Error: set_get_proxbox_item-1 - {}".format(e))
        print(e)
        config = None

    vcpus, memory_Mb, disk_Gb = get_resources(proxmox_json)

    proxbox_vm = ProxmoxVM.objects.filter(domain=domain, name=proxmox_vm_name).first()
    if proxbox_vm is None:
        proxbox_vm = ProxmoxVM.objects.filter(domain=domain, proxmox_vm_id=vmid).first()

    if proxbox_vm is None:
        proxbox_vm = ProxmoxVM(
            name=proxmox_vm_name,
            proxmox_vm_id=vmid,
            type=vm_type
        )
        proxbox_vm.save()
    if proxbox_vm:
        proxbox_vm.instance_data = proxmox_json,
        proxbox_vm.config_data = config
        proxbox_vm.url = 'https://{}:{}/#v1:0:={}%2F{} '.format(domain, port, vm_type, vmid)
        proxbox_vm.latest_job = job_id
        proxbox_vm.latest_update = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
        proxbox_vm.cluster_id = cluster.id
        proxbox_vm.cluster = cluster
        proxbox_vm.node = node
        proxbox_vm.vcpus = vcpus
        proxbox_vm.memory = memory_Mb
        proxbox_vm.disk = disk_Gb
        proxbox_vm.proxmox_vm_id = vmid
        proxbox_vm.domain = domain

        netbox_vm = get_set_vm(cluster, proxmox_json)
        proxbox_vm.virtual_machine_id = netbox_vm.id
        proxbox_vm.virtual_machine = netbox_vm

        proxbox_vm.save()

    return proxbox_vm


def set_get_proxbox_from_vm(vm, domain, node, vmid, job_id, cluster, type, config):
    proxmox_session = get_session(domain)
    port = proxmox_session.get("PROXMOX_PORT", "8006")

    vcpus = vm.vcpus
    memory_Mb = vm.memory
    disk_Gb = vm.disk
    proxbox_vm = ProxmoxVM.objects.filter(domain=domain, name=vm.name).first()
    if proxbox_vm is None:
        proxbox_vm = ProxmoxVM.objects.filter(domain=domain, proxmox_vm_id=vmid).first()

    if proxbox_vm is None:
        proxbox_vm = ProxmoxVM(
            name=vm.name,
            proxmox_vm_id=vmid,
            type=type
        )
        proxbox_vm.save()
    if proxbox_vm:
        proxbox_vm.config_data = config
        proxbox_vm.url = 'https://{}:{}/#v1:0:={}%2F{} '.format(domain, port, type, vmid)
        proxbox_vm.latest_job = job_id
        proxbox_vm.latest_update = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
        proxbox_vm.cluster_id = cluster.id
        proxbox_vm.cluster = cluster
        proxbox_vm.node = node
        proxbox_vm.vcpus = vcpus
        proxbox_vm.memory = memory_Mb
        proxbox_vm.disk = disk_Gb
        proxbox_vm.proxmox_vm_id = vmid
        proxbox_vm.domain = domain

        proxbox_vm.virtual_machine_id = vm.id
        proxbox_vm.virtual_machine = vm

        proxbox_vm.save()

    return proxbox_vm
