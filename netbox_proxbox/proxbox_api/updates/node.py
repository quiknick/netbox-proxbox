from dcim.choices import InterfaceTypeChoices

from .. import (
    create,
)
from ..plugins_config import (
    # PROXMOX,
    # PROXMOX_PORT,
    # PROXMOX_USER,
    # PROXMOX_PASSWORD,
    # PROXMOX_SSL,
    # NETBOX,
    # NETBOX_TOKEN,
    # PROXMOX_SESSION as proxmox,
    PROXMOX_SESSIONS as proxmox_sessions,
    NETBOX_SESSION as nb,
)


# Update STATUS field on /dcim/device/{id}
def status(netbox_node, proxmox_node):
    #
    # Compare STATUS
    #
    if proxmox_node['online'] == 1:
        # If Proxmox is 'online' and Netbox is 'offline', update it.
        if netbox_node.status.value == 'offline':
            netbox_node.status.value = 'active'

            if netbox_node.save() == True:
                status_updated = True
            else:
                status_updated = False

        else:
            status_updated = False


    elif proxmox_node['online'] == 0:
        # If Proxmox is 'offline' and Netbox' is 'active', update it.
        if netbox_node.status.value == 'active':
            netbox_node.status.value = 'offline'

            if netbox_node.save() == True:
                status_updated = True
            else:
                status_updated = False

        else:
            status_updated = False

    else:
        status_updated = False

    return status_updated


def get_set_interface(name, netbox_node):
    dev_interface = nb.dcim.interfaces.get(name=name, device_id=netbox_node.id)
    if dev_interface is None:
        # new_interface_json = {"device_id": netbox_node.id, "name": name, type: InterfaceTypeChoices.TYPE_LAG}
        intf_dict = dict(
            name=name,
            form_factor=0,
            description="LAG",
            device=netbox_node.id,
            type=InterfaceTypeChoices.TYPE_LAG
        )
        dev_interface = nb.dcim.interfaces.create(intf_dict)

    return dev_interface


# Assing node ip if it doesn't have it
def interface_ip_assign(netbox_node, proxmox_json):
    ip = proxmox_json.get("ip", None)
    try:
        node_interface = get_set_interface('Bond0', netbox_node)
        netbox_ip = nb.ipam.ip_addresses.get(address=ip)
        if netbox_ip is None:
            # Create the ip address and link it to the interface previously created
            address = {
                "address": ip,
                "assigned_object_type": "dcim.interface",
                "assigned_object_id": node_interface.id
            }
            netbox_ip = nb.ipam.ip_addresses.create(address)
        else:
            try:
                netbox_ip.assigned_object_type = "dcim.interface"
                netbox_ip.assigned_object_id = node_interface.id
                netbox_ip.assigned_object = node_interface
                netbox_ip.save()
            except Exception as e:
                print(e)
        # Associate the ip address to the vm
        netbox_node.primary_ip = netbox_ip
        if netbox_ip.family.label == 'IPv4':
            netbox_node.primary_ip4 = netbox_ip
        else:
            netbox_node.primary_ip6 = netbox_ip
        netbox_node.save()
        return True
    except Exception as e:
        print(e)
        return False


# Update CLUSTER field on /dcim/device/{id}
def cluster(proxmox, netbox_node, proxmox_node, proxmox_cluster):
    #
    # Compare CLUSTER
    #
    if proxmox_cluster != None:
        # If cluster is filled, but different from actual cluster, update it.
        if netbox_node.cluster.name != proxmox_cluster['name']:
            # Search for Proxmox Cluster using create.cluster() function
            cluster_id = create.virtualization.cluster(proxmox).id

            # Use Cluster ID to update NODE information
            netbox_node.cluster.id = cluster_id

            if netbox_node.save() == True:
                cluster_updated = True
            else:
                cluster_updated = False

        else:
            cluster_updated = False

    # If cluster is empty, update it.
    elif proxmox_cluster == None:
        # Search for Proxmox Cluster using create.cluster() function
        cluster_id = create.virtualization.cluster(proxmox).id

        # Use Cluster ID to update NODE information
        netbox_node.cluster.id = cluster_id

        if netbox_node.save() == True:
            cluster_updated = True
        else:
            cluster_updated = False

    # If cluster was not empty and also not different, do not make any change.
    else:
        cluster_updated = False

    return cluster_updated
