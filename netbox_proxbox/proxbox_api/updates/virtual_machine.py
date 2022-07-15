import requests
import json
import re

from django.template.defaultfilters import slugify

# PLUGIN_CONFIG variables
from ..plugins_config import (
    # PROXMOX,
    # PROXMOX_PORT,
    # PROXMOX_USER,
    # PROXMOX_PASSWORD,
    # PROXMOX_SSL,
    NETBOX,
    NETBOX_TOKEN,
    NETBOX_TENANT_NAME,
    NETBOX_TENANT_REGEX_VALIDATOR,
    NETBOX_VM_ROLE_ID,
    NETBOX_VM_ROLE_NAME,
    NETBOX_SESSION as nb,
)

from .. import (
    create,
)

ipv4_regex = r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(\/\d{1,3})?"
ipv6_regex = r"([a-zA-Z0-9]{1,4}(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?:([a-zA-Z0-9]{0,4})?:([a-zA-Z0-9]{0,4})?(\.\d{1,3}\.\d{1,3}\.\d{1,3})?(\/\d{1,3})?)"


# Update "status" field on Netbox Virtual Machine based on Proxmox information
def status(netbox_vm, proxmox_vm):
    status_updated, netbox_vm = base_status(netbox_vm, proxmox_vm)
    return status_updated


def base_status(netbox_vm, proxmox_vm):
    # False = status not changed on Netbox
    # True  = status changed on Netbox
    status_updated = False

    # [ running, stopped ]
    proxmox_status = proxmox_vm['status']

    # [ offline, active, planned, staged, failed, decommissioning ]
    netbox_status = netbox_vm.status.value

    if (proxmox_status == 'running' and netbox_status == 'active') or (
            proxmox_status == 'stopped' and netbox_status == 'offline'):
        # Status not updated
        status_updated = False

    # Change status to active on Netbox if it's offline
    elif proxmox_status == 'stopped' and netbox_status == 'active':
        netbox_vm.status.value = 'offline'
        netbox_vm.save()

        # Status updated
        status_updated = True

    # Change status to offline on Netbox if it's active
    elif proxmox_status == 'running' and netbox_status == 'offline':
        netbox_vm.status.value = 'active'
        netbox_vm.save()

        # Status updated
        status_updated = True

    # Status not expected
    else:
        # Status doesn't need to change
        status_updated = False

    return status_updated, netbox_vm


def site(**kwargs):
    # If site_id equals to 0, consider it is not configured by user and must be created by Proxbox
    site_id = kwargs.get('site_id', 0)


def update_vm_role(netbox_vm, proxmox_vm):
    vm_type = proxmox_vm['type']
    role_name = NETBOX_VM_ROLE_NAME
    try:
        if vm_type == 'qemu':
            role_name = "VPS"
        if vm_type == 'lxc':
            role_name = "LXC"
    except  Exception as e:
        pass
    role = create.extras.role(role_id=NETBOX_VM_ROLE_ID, role_name=role_name)
    netbox_vm.role_id = role.id
    netbox_vm.role = role
    netbox_vm.save()
    return True, netbox_vm


# Function that modifies 'custom_field' of Netbox Virtual Machine.
# It uses HTTP Request and not Pynetbox (as I was not able to).
def http_update_custom_fields(**kwargs):
    # Saves kwargs variables
    domain_with_http = kwargs.get('domain_with_http')
    token = kwargs.get('token')
    vm_id = kwargs.get('vm_id', 0)
    vm_name = kwargs.get('vm_name')
    vm_cluster = kwargs.get('vm_cluster')
    custom_fields = kwargs.get('custom_fields')

    #
    # HTTP PATCH Request (partially update)
    #
    # URL 
    url = '{}/api/virtualization/virtual-machines/{}/'.format(domain_with_http, vm_id)

    # HTTP Request Headers
    headers = {
        "Authorization": "Token {}".format(token),
        "Content-Type": "application/json"
    }

    # HTTP Request Body
    body = {
        "name": vm_name,
        "cluster": vm_cluster,
        "custom_fields": custom_fields
    }

    # Makes the request and saves it to var
    r = requests.patch(url, data=json.dumps(body), headers=headers)

    # Return HTTP Status Code
    return r.status_code


def http_contact_assing(**kwargs):
    # Saves kwargs variables
    domain_with_http = kwargs.get('domain_with_http')
    token = kwargs.get('token')
    tenant_id = kwargs.get('tenant_id')
    contact_id = kwargs.get('contact_id')
    role_id = kwargs.get('role_id')
    content_type = kwargs.get('content_type')

    #
    # HTTP PATCH Request (partially update)
    #
    # URL
    url = '{}/api/tenancy/contact-assignments/'.format(domain_with_http)

    # HTTP Request Headers
    headers = {
        "Authorization": "Token {}".format(token),
        "Content-Type": "application/json"
    }

    # HTTP Request Body
    body = {
        "object_id": tenant_id,
        "contact": contact_id,
        "role": role_id,
        "content_type": content_type
    }

    # Makes the request and saves it to var
    r = requests.post(url, data=json.dumps(body), headers=headers)

    # Return HTTP Status Code
    return r.status_code


# Update 'custom_fields' field on Netbox Virtual Machine based on Proxbox
def custom_fields(netbox_vm, proxmox_vm):
    s, netbox_vm = base_custom_fields(netbox_vm, proxmox_vm)
    return s


def base_custom_fields(netbox_vm, proxmox_vm):
    # Create the new 'custom_field' with info from Proxmox
    custom_fields_update = {}

    # Check if there is 'custom_field' configured on Netbox
    if len(netbox_vm.custom_fields) == 0:
        print("[ERROR] There's no 'Custom Fields' registered by the Netbox Plugin user")

    # If any 'custom_field' configured, get it and update, if necessary.
    elif len(netbox_vm.custom_fields) > 0:

        # Get current configured custom_fields
        custom_fields_names = list(netbox_vm.custom_fields.keys())

        #
        # VERIFY IF CUSTOM_FIELDS EXISTS AND THEN UPDATE INFORMATION, IF NECESSARY.
        #
        # Custom Field 'proxmox_id'
        if 'proxmox_id' in custom_fields_names:
            if netbox_vm.custom_fields.get("proxmox_id") != proxmox_vm['vmid']:
                custom_fields_update["proxmox_id"] = proxmox_vm['vmid']
        else:
            print("[ERROR] 'proxmox_id' custom field not registered yet or configured incorrectly]")

        # Custom Field 'proxmox_node'
        if 'proxmox_node' in custom_fields_names:
            if netbox_vm.custom_fields.get("proxmox_node") != proxmox_vm['node']:
                custom_fields_update["proxmox_node"] = proxmox_vm['node']
        else:
            print("[ERROR] 'proxmox_node' custom field not registered yet or configured incorrectly")

        # Custom Field 'proxmox_type'
        if 'proxmox_type' in custom_fields_names:
            if netbox_vm.custom_fields.get("proxmox_type") != proxmox_vm['type']:
                custom_fields_update["proxmox_type"] = proxmox_vm['type']
        else:
            print("[ERROR] 'proxmox_type' custom field not registered yet or configured incorrectly")

        # Only updates information if changes found
        if len(custom_fields_update) > 0:

            # As pynetbox does not have a way to update custom_fields, use API HTTP request
            custom_field_updated = http_update_custom_fields(
                domain_with_http=NETBOX,
                token=NETBOX_TOKEN,
                vm_id=netbox_vm.id,
                vm_name=netbox_vm.name,
                vm_cluster=netbox_vm.cluster.id,
                custom_fields=custom_fields_update
            )

            # Verify HTTP reply CODE
            if custom_field_updated != 200:
                print(
                    "[ERROR] Some error occured trying to update 'custom_fields' through HTTP Request. HTTP Code: {}. -> {}".format(
                        custom_field_updated, netbox_vm.name))
                return False, netbox_vm

            else:
                # If none error occured, considers VM updated.
                return True, netbox_vm

        return False, netbox_vm


# Update 'local_context_data' field on Netbox Virtual Machine based on Proxbox
def local_context_data(netbox_vm, proxmox_vm, PROXMOX, PROXMOX_PORT):
    s, netbox_vm = base_local_context_data(netbox_vm, proxmox_vm, PROXMOX, PROXMOX_PORT)
    return s


def base_local_context_data(netbox_vm, proxmox_vm, PROXMOX, PROXMOX_PORT):
    current_local_context = netbox_vm.local_context_data

    proxmox_values = {}

    # Add and change values from Proxmox
    proxmox_values["name"] = proxmox_vm["name"]
    proxmox_values["url"] = "https://{}:{}".format(PROXMOX, PROXMOX_PORT)  # URL
    proxmox_values["id"] = proxmox_vm["vmid"]  # VM ID
    proxmox_values["node"] = proxmox_vm["node"]
    proxmox_values["type"] = proxmox_vm["type"]

    maxmem = int(int(proxmox_vm["maxmem"]) / 1000000000)  # Convert bytes to gigabytes
    proxmox_values["memory"] = "{} {}".format(maxmem, 'GB')  # Add the 'GB' unit of measurement

    maxdisk = int(int(proxmox_vm["maxdisk"]) / 1000000000)  # Convert bytes to gigabytes
    proxmox_values["disk"] = "{} {}".format(maxdisk, 'GB')  # Add the 'GB' unit of measurement

    proxmox_values["vcpu"] = proxmox_vm["maxcpu"]  # Add the 'GB' unit of measurement

    # Verify if 'local_context' is empty and if true, creates initial values.
    if current_local_context == None:
        netbox_vm.local_context_data = {"proxmox": proxmox_values}
        netbox_vm.save()
        return True, netbox_vm

    # Compare current Netbox values with Porxmox values
    elif current_local_context.get('proxmox') != proxmox_values:
        # Update 'proxmox' key on 'local_context_data'
        current_local_context.update(proxmox=proxmox_values)

        netbox_vm.local_context_data = current_local_context
        netbox_vm.save()
        return True, netbox_vm

    # If 'local_context_data' already updated
    else:
        return False, netbox_vm

    return False, netbox_vm


# Updates following fields based on Proxmox: "vcpus", "memory", "disk", if necessary.
def resources(netbox_vm, proxmox_vm):
    s, netbox_vm = resources(netbox_vm, proxmox_vm)
    return s


def base_resources(netbox_vm, proxmox_vm):
    # Save values from Proxmox
    vcpus = float(proxmox_vm["maxcpu"])

    # Convert bytes to megabytes and then convert float to integer
    memory_Mb = proxmox_vm["maxmem"]
    memory_Mb = int(memory_Mb / 1048576)

    # Convert bytes to gigabytes and then convert float to integer
    disk_Gb = proxmox_vm["maxdisk"]
    disk_Gb = int(disk_Gb / 1000000000)

    # JSON with new resources info
    new_resources_json = {}

    # Compare VCPU
    if netbox_vm.vcpus != None:
        # Convert Netbox VCPUs to float, since it is coming as string from Netbox
        netbox_vm.vcpus = float(netbox_vm.vcpus)

        if netbox_vm.vcpus != vcpus:
            new_resources_json["vcpus"] = vcpus

    elif netbox_vm.vcpus == None:
        new_resources_json["vcpus"] = vcpus

    # Compare Memory
    if netbox_vm.memory != None:
        if netbox_vm.memory != memory_Mb:
            new_resources_json["memory"] = memory_Mb

    elif netbox_vm.memory == None:
        new_resources_json["memory"] = memory_Mb

    # Compare Disk
    if netbox_vm.disk != None:
        if netbox_vm.disk != disk_Gb:
            new_resources_json["disk"] = disk_Gb

    elif netbox_vm.disk == None:
        new_resources_json["disk"] = disk_Gb

    # If new information found, save it to Netbox object.
    if len(new_resources_json) > 0:
        resources_updated = netbox_vm.update(new_resources_json)

        if resources_updated == True:
            return True, netbox_vm
        else:
            return False, netbox_vm
    return False, netbox_vm


# def get_ip(proxmox, node, vmid, type):
#     test_str = None
#     try:
#         if type == 'qemu':
#             config1 = proxmox.nodes(node).qemu(vmid).config.get()
#             test_str = config1['ipconfig0']
#         if type == 'lxc':
#             config2 = proxmox.nodes(node).lxc(vmid).config.get()
#             test_str = config2['net0']
#     except Exception as e:
#         test_str = None
#         pass
#     if test_str is None:
#         return None
#
#     regex = r"ip=\d(\d)?(\d)?.\d(\d)?(\d)?.\d(\d)?(\d)?.\d(\d)?(\d)?(\/(\d)?(\d)?(\d)?)?"
#
#     # test_str = "name=eth0,bridge=vmbr504,firewall=1,gw=172.16.19.1,hwaddr=5A:70:3F:05:0D:AC,ip=172.16.19.251/24,type=veth"
#     try:
#         matches = re.finditer(regex, test_str, re.MULTILINE)
#         it = matches.__next__()
#         ip = it.group().replace('ip=', '').strip()
#         return ip
#     except Exception as e:
#         return None
#         pass

def get_ip(test_str):
    print('[OK] parsing ipv4. -> {}'.format(test_str))
    regex = r"ip=" + ipv4_regex
    # test_str = "name=eth0,bridge=vmbr504,firewall=1,gw=172.16.19.1,hwaddr=5A:70:3F:05:0D:AC,ip=172.16.19.251/24,type=veth"
    try:
        matches = re.finditer(regex, test_str, re.MULTILINE)
        it = matches.__next__()
        ip = it.group().replace('ip=', '').strip()
        print('[OK] Parse. -> {}'.format(ip))
        return ip
    except Exception as e:
        return None
        pass


def get_ipv6(test_str):
    # ipv6 regex
    print('[OK] parsing ipv6. -> {}'.format(test_str))
    regex = r"ip6=" + ipv6_regex

    # test_str = "name=eth0,bridge=vmbr502,gw=172.16.17.1,gw6=fc00:16:17::1,hwaddr=CA:F3:00:D6:31:2A,ip=172.16.17.203/24,ip6=2001:db8:3:4::192.0.2.33/64,type=veth"
    try:
        matches = re.finditer(regex, test_str, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        ip = it.group().replace('ip6=', '').strip()
        print('[OK] Parse. -> {}'.format(ip))
        return ip
    except Exception as e:
        return None
        pass


def get_main_ip(test_str):
    ipv4 = None
    ipv6 = None

    try:
        print('[OK] Parsing main ip for ipv4 -> {}').format(test_str)
        rgx = r"main(\s)?ip:(\s)?"
        matches = re.finditer(rgx + ipv4_regex, test_str, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        ipv4 = it.group().lower() \
            .replace('mainip:', '') \
            .replace('mainip: ', '') \
            .replace('main ip:', '') \
            .replace('main ip: ', '') \
            .strip()
        ipv4 = (re.sub(rgx, '', ipv4)).strip()
    except Exception as e:
        pass
    try:
        print('[OK] Parsing main ip for ipv6')
        rgx = r"main(\s)?ip:(\s)?"
        matches = re.finditer(rgx + ipv6_regex, test_str, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        ipv6 = it.group().lower() \
            .replace('mainip:', '') \
            .replace('mainip: ', '') \
            .replace('main ip:', '') \
            .replace('main ip: ', '') \
            .strip()
        ipv6 = (re.sub(rgx, '', ipv6)).strip()
    except Exception as e:
        pass
    try:
        if ipv4 is None:
            print('[OK] Parsing ip address allocation for ipv4')
            rgx = r"ip(\s)?address(\s)?allocation:(\s)?"
            matches = re.finditer(rgx + ipv4_regex, test_str, re.MULTILINE | re.IGNORECASE)
            it = matches.__next__()
            ipv4 = it.group().lower() \
                .replace('ipaddressallocation:', '') \
                .replace('ipaddressallocation :', '') \
                .replace('ip addressallocation:', '') \
                .replace('ip addressallocation :', '') \
                .replace('ip address allocation:', '') \
                .replace('ip address allocation :', '') \
                .strip()
            ipv4 = (re.sub(rgx, '', ipv4)).strip()
    except Exception as e:
        pass
    try:
        if ipv6 is None:
            print('[OK] Parsing ip address allocation for ipv6')
            rgx = r"ip(\s)?address(\s)?allocation:(\s)?"
            matches = re.finditer(rgx + ipv6_regex, test_str, re.MULTILINE | re.IGNORECASE)
            it = matches.__next__()
            ipv6 = it.group().lower() \
                .replace('ipaddressallocation:', '') \
                .replace('ipaddressallocation :', '') \
                .replace('ip addressallocation:', '') \
                .replace('ip addressallocation :', '') \
                .replace('ip address allocation:', '') \
                .replace('ip address allocation :', '') \
                .strip()
            ipv6 = (re.sub(rgx, '', ipv6)).strip()
    except Exception as e:
        pass
    return ipv4, ipv6


def set_ipv4(netbox_vm, vm_interface, ipv4):
    if ipv4 is not None:
        if netbox_vm.primary_ip4 is None:
            # Create the ip address and link it to the interface previously created
            address = {
                "address": ipv4,
                "assigned_object_type": "virtualization.vminterface",
                "assigned_object_id": vm_interface.id
            }
            netbox_ip = nb.ipam.ip_addresses.create(address)
            # Associate the ip address to the vm
            netbox_vm.primary_ip = netbox_ip
            netbox_vm.primary_ip4 = netbox_ip
            # netbox_vm.save()
        else:
            id = netbox_vm.primary_ip4.id
            current_ip = nb.ipam.ip_addresses.get(id=id)
            current_ip.address = ipv4
            current_ip.save()
            netbox_vm.primary_ip = current_ip
            netbox_vm.primary_ip4 = current_ip
            # netbox_vm.save()
    return netbox_vm


def set_ipv6(netbox_vm, vm_interface, ipv6):
    if ipv6 is not None:
        if netbox_vm.primary_ip6 is None:
            # Create the ip address and link it to the interface previously created
            address = {
                "address": ipv6,
                "assigned_object_type": "virtualization.vminterface",
                "assigned_object_id": vm_interface.id
            }
            netbox_ip = nb.ipam.ip_addresses.create(address)
            # Associate the ip address to the vm
            netbox_vm.primary_ip = netbox_ip
            netbox_vm.primary_ip6 = netbox_ip
            # netbox_vm.save()
        else:
            id = netbox_vm.primary_ip6.id
            current_ip = nb.ipam.ip_addresses.get(id=id)
            current_ip.address = ipv6
            current_ip.save()
            if netbox_vm.primary_ip6 is None:
                netbox_vm.primary_ip = current_ip
            netbox_vm.primary_ip6 = current_ip
            # netbox_vm.save()

    return netbox_vm


def get_set_interface(name, virtual_machine):
    vm_interface = nb.virtualization.interfaces.get(name=name, virtual_machine_id=virtual_machine)
    if vm_interface is None:
        new_interface_json = {"virtual_machine": virtual_machine, "name": name}
        vm_interface = nb.virtualization.interfaces.create(new_interface_json)

    return vm_interface


def client_tenant_parser(test_str):
    client = None
    tenant_name = None
    client_regex = r"client(\s)?(:)?.*(id)?:"
    try:
        matches = re.finditer(client_regex, test_str, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        client = it.group() \
            .replace('client:', '') \
            .replace('client :', '') \
            .replace('Client:', '') \
            .replace('Client :', '') \
            .replace('id:', '') \
            .replace('id :', '') \
            .replace('(id :', '') \
            .replace('(ID:', '') \
            .replace('Id:', '') \
            .replace('Id :', '') \
            .replace('(Id :', '') \
            .replace('(ID :', '') \
            .strip()
        sub_str_regex = r"\(.*\)"
        m_result = None
        try:
            m_result = re.finditer(sub_str_regex, client, re.MULTILINE | re.IGNORECASE).__next__().group().strip()
        except Exception as e:
            print(e)
            pass
        if m_result:
            if m_result.replace('(', '').replace(')', '').strip():
                tenant_name = m_result.replace('(', '').replace(')', '').strip()
            client = client.replace(m_result, '').strip()
        else:
            tenant_name = client
        print('[OK] Tenant parse. -> {}'.format(client))
    except Exception as e:
        pass
    return tenant_name, client


def get_set_tenant_from_configuration(test_str):
    tenant_name, client = client_tenant_parser(test_str)
    nb_tenant = nb.tenancy.tenants.get(name=tenant_name)
    if nb_tenant is None:
        new_tenant = {"name": tenant_name, "slug": slugify(tenant_name)}
        nb_tenant = nb.tenancy.tenants.create(new_tenant)
    set_assign_contact(test_str, client, nb_tenant.id, 'tenancy.tenant')
    return nb_tenant


def contact_parse_set(test_str, name):
    contact = None
    contact_role = None
    try:
        print('[OK] Parsing contact from. -> {}'.format(test_str))
        contact_email = None
        contact_regex = r"email(\s)?(:)?(\s)?\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+"
        try:
            matches = re.finditer(contact_regex, test_str, re.MULTILINE | re.IGNORECASE)
            it = matches.__next__()
            contact_email = it.group() \
                .replace('email:', '') \
                .replace('email :', '') \
                .replace('Email:', '') \
                .replace('Email :', '') \
                .strip()
            print('[OK] Contact email parsed. -> {}'.format(contact_email))
        except Exception as e:
            print(e)
        if contact_email is None:
            return None, None

        contact = nb.tenancy.contacts.get(email=contact_email)
        if contact is None:
            print('[OK] Creating contact for {} with email {}'.format(name, contact_email))
            new_contact = {"name": name, "email": contact_email}
            contact = nb.tenancy.contacts.create(new_contact)

        contact_role = nb.tenancy.contact_roles.get(name="vm")
        if contact_role is None:
            print('[OK] Creating role. -> {}'.format("vm"))
            new_contact_role = {"name": "vm", "slug": slugify("vm")}
            contact_role = nb.tenancy.contact_roles.create(new_contact_role)
    except Exception as e:
        print(e)

    return contact, contact_role


def set_contact_to_vm(test_str, netbox_vm):
    content_type = 'virtualization.virtualmachine'
    try:
        print('[OK] Parsing contact from. -> {}'.format(test_str))
        tenant = netbox_vm.tenant
        tenant_name, client = client_tenant_parser(test_str)
        set_assign_contact(test_str, client, netbox_vm.id, content_type)
        return netbox_vm
    except Exception as e:
        print(e)
        return netbox_vm


def set_assign_contact(test_str, name, object_id, content_type='tenancy.tenant'):
    contact = None
    contact_role = None
    contact_assigment = None
    try:
        contact, contact_role = contact_parse_set(test_str, name)
        if not (contact and contact_role):
            return contact, contact_role, contact_assigment
        contact_assigment = nb.tenancy.contact_assignments.get(object_id=object_id,
                                                               contact_id=contact.id,
                                                               content_type=content_type,
                                                               role_id=contact_role.id)
        if contact_assigment is None:
            print('[OK] Assigning contact {} to tenant {}'.format(contact.name, name))

            new_contact_assigment = {"object_id": object_id,
                                     "contact": contact.id,
                                     "content_type": content_type,
                                     "contact_id": contact.id,
                                     "role": contact_role.id,
                                     "priority": "primary"
                                     }
            contact_assigment = nb.tenancy.contact_assignments.create(new_contact_assigment)
            print('[OK] Contact assigned {} to tenant {}'.format(contact.name, name))
            # assign_contact_to_tenant(tenant, contact, contact_role, content_type)
    except Exception as e:
        print(e)
    return contact, contact_role, contact_assigment


def get_set_tenant_group(tenant, netbox_vm):
    tags = netbox_vm.tags
    tags_name = []
    tenant_group_name = 'Customers'
    for tag in tags:
        if 'proxbox' == tag.name.lower():
            pass
        else:
            tags_name.append(tag.name.lower())
    if NETBOX_TENANT_NAME is not None and NETBOX_TENANT_NAME.lower() in tags_name:
        tenant_group_name = NETBOX_TENANT_NAME
    tenant_group = nb.tenancy.tenant_groups.get(name=tenant_group_name)
    if tenant_group is None:
        new_tenant_group = {"name": tenant_group_name, "slug": slugify(tenant_group_name)}
        tenant_group = nb.tenancy.contact_roles.create(new_tenant_group)
    tenant.group_id = tenant_group.id
    tenant.group = tenant_group
    tenant.save()
    return tenant


def set_tenant(netbox_vm, observation):
    print('[OK] Getting tenant from. -> {}'.format(observation))
    tenant = get_set_tenant_from_configuration(observation)
    if tenant is None:
        return netbox_vm
    tenant = get_set_tenant_group(tenant, netbox_vm)

    netbox_vm.tenant_id = tenant.id
    netbox_vm.tenant = tenant
    if observation:
        netbox_vm.comments = observation
    netbox_vm.save()

    return netbox_vm


def add_ip(proxmox, netbox_vm, proxmox_vm):
    s, netbox_vm = base_add_ip(proxmox, netbox_vm, proxmox_vm)
    return s


def base_add_ip(proxmox, netbox_vm, proxmox_vm):
    vm_type = proxmox_vm['type']
    vmid = proxmox_vm['vmid']
    node = proxmox_vm['node']
    config = None
    network_str = None
    ipv4 = None
    ipv6 = None
    try:
        if vm_type == 'qemu':
            config = proxmox.nodes(node).qemu(vmid).config.get()
            print('[OK] Got Configuration for quemu. -> {}'.format(vmid))
        if vm_type == 'lxc':
            config = proxmox.nodes(node).lxc(vmid).config.get()
            print('[OK] Got Configuration for lxc. -> {}'.format(vmid))
    except  Exception as e:
        print(e)
        config = None

    if config is None:
        return False, netbox_vm

    try:
        if vm_type == 'qemu':
            if 'ipconfig0' in config:
                network_str = config['ipconfig0']
            elif 'net0' in config:
                network_str = config['net0']
        if vm_type == 'lxc':
            if 'net0' in config:
                network_str = config['net0']
            elif 'ipconfig0' in config:
                network_str = config['ipconfig0']
    except  Exception as e:
        network_str = None

    try:
        if network_str is not None:
            ipv4 = get_ip(network_str)
            ipv6 = get_ipv6(network_str)
            if ipv4 is None and ipv6 is None:
                print('[OK] ipv4 or ipv6 not found searching in the observations for . -> {}'.format(vmid))
                if 'description' in config:
                    ipv4, ipv6 = get_main_ip(config['description'])
            if not (ipv4 is None and ipv6 is None):
                virtual_machine = netbox_vm.id
                name = 'eth0'
                # Create the interface if doesn't exists
                try:
                    vm_interface = get_set_interface(name, virtual_machine)
                    netbox_vm = set_ipv6(netbox_vm, vm_interface, ipv6)
                    netbox_vm = set_ipv4(netbox_vm, vm_interface, ipv4)
                except Exception as e:
                    print(e)
                netbox_vm.save()
    except Exception as e:
        print(e)
    return True, netbox_vm


def add_configuration(proxmox, netbox_vm, proxmox_vm):
    s, netbox_vm = base_add_configuration(proxmox, netbox_vm, proxmox_vm)
    return s


def default_tenant(netbox_vm):
    has_string = False
    try:
        rgx = r"" + NETBOX_TENANT_REGEX_VALIDATOR
        matches = re.finditer(rgx, netbox_vm.name, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        it.group().lower().strip()
        has_string = True
    except Exception as e:
        print(e)
    if has_string:
        if NETBOX_TENANT_NAME is not None:
            nb_tenant = nb.tenancy.tenants.get(name=NETBOX_TENANT_NAME)
            if nb_tenant is None:
                new_tenant = {"name": NETBOX_TENANT_NAME, "slug": slugify(NETBOX_TENANT_NAME)}
                nb_tenant = nb.tenancy.tenants.create(new_tenant)
            if nb_tenant is not None:
                nb_tenant = get_set_tenant_group(nb_tenant, netbox_vm)
                netbox_vm.tenant_id = nb_tenant.id
                netbox_vm.tenant = nb_tenant
                netbox_vm.save()

    return netbox_vm


def base_add_configuration(proxmox, netbox_vm, proxmox_vm):
    vm_type = proxmox_vm['type']
    vmid = proxmox_vm['vmid']
    node = proxmox_vm['node']
    config = None
    try:
        if NETBOX_TENANT_NAME is not None:
            netbox_vm = default_tenant(netbox_vm)
    except Exception as e:
        print(e)
    try:
        if vm_type == 'qemu':
            config = proxmox.nodes(node).qemu(vmid).config.get()
            print('[OK] Got Configuration for quemu. -> {}'.format(vmid))
        if vm_type == 'lxc':
            config = proxmox.nodes(node).lxc(vmid).config.get()
            print('[OK] Got Configuration for lxc. -> {}'.format(vmid))
    except Exception as e:
        print(e)
        config = None

    if config is None:
        return False, netbox_vm

    try:
        if 'description' in config:
            netbox_vm = set_tenant(netbox_vm, config['description'])
            netbox_vm = set_contact_to_vm(config['description'], netbox_vm)
        else:
            print('no description')
    except Exception as e:
        print(e)
    return True, netbox_vm
