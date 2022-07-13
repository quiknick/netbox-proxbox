# PLUGIN_CONFIG variables
from django.template.defaultfilters import slugify

from ..plugins_config import (
    NETBOX_SESSION as nb,
    NETBOX_NODE_ROLE_ID,
    NETBOX_SITE_ID,
)

from . import (
    extras,
    virtualization,
)


#
# dcim.manufacturers
#
def manufacturer():
    # TODO: make sure the configuration of the manufacturer can be set on the config file
    # proxbox_manufacturer_name = 'Proxbox Basic Manufacturer'
    # proxbox_manufacturer_slug = 'proxbox-manufacturer'
    # proxbox_manufacturer_desc = 'Manufacturer Proxbox will use if none is configured by user in PLUGINS_CONFIG'

    proxbox_manufacturer_name = 'Dell'
    proxbox_manufacturer_slug = slugify(proxbox_manufacturer_name)
    proxbox_manufacturer_desc = 'Manufacturer Proxbox will use if none is configured by user in PLUGINS_CONFIG'

    # Check if Proxbox manufacturer already exists.
    proxbox_manufacturer = nb.dcim.manufacturers.get(
        name=proxbox_manufacturer_name,
        slug=proxbox_manufacturer_slug,
    )

    if proxbox_manufacturer == None:
        try:
            # If Proxbox manufacturer does not exist, create one.
            manufacturer = nb.dcim.manufacturers.create(
                name=proxbox_manufacturer_name,
                slug=proxbox_manufacturer_slug,
                description=proxbox_manufacturer_desc
            )
        except:
            return "Error creating the '{0}' manufacturer. Possible errors: the name '{0}' or slug '{1}' is already used.".format(
                proxbox_manufacturer_name, proxbox_manufacturer_slug)

    else:
        manufacturer = proxbox_manufacturer

    return manufacturer


#
# dcim.device_types
#
def device_type():
    proxbox_device_type_model = 'Proxbox Model'
    proxbox_device_type_slug = 'proxbox-model'
    proxbox_device_type_comments = "Device Type Proxbox will use when creating the Cluster's Nodes. When the Node is created, you can change the device type to the actual server model."

    # Check if Proxbox manufacturer already exists.
    proxbox_device_types = nb.dcim.device_types.get(
        model=proxbox_device_type_model,
        slug=proxbox_device_type_slug
    )

    if proxbox_device_types == None:
        try:
            # If Proxbox manufacturer does not exist, create one.
            device_type = nb.dcim.device_types.create(
                manufacturer=manufacturer().id,
                model=proxbox_device_type_model,
                slug=proxbox_device_type_slug,
                comments=proxbox_device_type_comments,
                tags=[extras.tag().id]
            )
        except:
            return "Error creating the '{0}' device type. Possible errors: the model '{0}' or slug '{1}' is already used.".format(
                proxbox_device_type_model, proxbox_device_type_slug)

    else:

        device_type = proxbox_device_types

    return device_type


#
# dcim.sites
#
def site(**kwargs):
    # If site_id equals to 0, consider it is not configured by user and must be created by Proxbox
    site_id = kwargs.get('site_id', 0)
    site_name = kwargs.get('site_name', None)
    if site_name:
        site = nb.dcim.sites.get(name=site_name)
        if site:
            return site

    if not isinstance(site_id, int):
        return 'Site ID must be INTEGER. Netbox PLUGINS_CONFIG is configured incorrectly.'

    # If user configured SITE_ID in Netbox's PLUGINS_CONFIG, use it.
    if site_id > 0:
        site = nb.dcim.sites.get(id=site_id)

        if site == None:
            return "Role ID of Virtual Machine or Node invalid. Maybe the ID passed does not exist or it is not a integer!"

    elif site_id == 0:
        site_proxbox_name = "Proxbox Basic Site"
        site_proxbox_slug = 'proxbox-basic-site'

        # Verify if basic site is already created
        site_proxbox = nb.dcim.sites.get(
            name=site_proxbox_name,
            slug=site_proxbox_slug
        )

        # Create a basic Proxbox site if not created yet.
        if site_proxbox == None:
            try:
                site = nb.dcim.sites.create(
                    name=site_proxbox_name,
                    slug=site_proxbox_slug,
                    status='active',
                    tags=[extras.tag().id]
                )
            except:
                return "Error creating the '{0}' site. Possible errors: the name '{0}' or slug '{1}' is already used.".format(
                    site_proxbox_name, site_proxbox_slug)

        # If basic site already created, use it.
        else:
            site = site_proxbox

    else:
        return 'Site ID configured is invalid.'

    return site


#
# dcim.devices (nodes)
#
def node(proxmox, proxmox_node, proxmox_session=None):
    role_id = NETBOX_NODE_ROLE_ID
    site_id = NETBOX_SITE_ID
    site_name = None
    role_name = None
    if proxmox_session:
        role_id = proxmox_session.get('NETBOX_NODE_ROLE_ID', role_id)
        site_id = proxmox_session.get('NETBOX_SITE_ID', site_id)
        site_name = proxmox_session.get('NETBOX_SITE_NAME', site_name)
        role_name = proxmox_session.get('NETBOX_NODE_ROLE_NAME', role_name)

    # Create json with basic NODE information

    node_json = {}
    node_json["name"] = proxmox_node['name']
    node_json["device_role"] = extras.role(role_id=role_id, role_name=role_name).id
    node_json["device_type"] = device_type().id
    node_json["site"] = site(site_id=site_id, site_name=site_name).id
    node_json["status"] = 'active'
    node_json["tags"] = [extras.tag().id]
    node_json["cluster"] = virtualization.cluster(proxmox).id

    # Create Node with json 'node_json'
    try:
        netbox_obj = nb.dcim.devices.create(node_json)

    except:
        print("[proxbox_api.create.node] Creation of NODE failed.")
        netbox_obj = None

    else:
        return netbox_obj

    # In case nothing works, returns error
    netbox_obj = None
    return netbox_obj
