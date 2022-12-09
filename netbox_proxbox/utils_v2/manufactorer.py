from django.template.defaultfilters import slugify

try:
    from dcim.models import Manufacturer

    from ..proxbox_api.plugins_config import (
        NETBOX_NODE_ROLE_ID,
        NETBOX_SITE_ID,
        NETBOX_MANUFACTURER
    )

except Exception as e:
    print(e)
    raise e


def get_set_manufacturer():
    # proxbox_manufacturer_name = 'Proxbox Basic Manufacturer'
    # proxbox_manufacturer_slug = 'proxbox-manufacturer'
    # proxbox_manufacturer_desc = 'Manufacturer Proxbox will use if none is configured by user in PLUGINS_CONFIG'

    proxbox_manufacturer_name = NETBOX_MANUFACTURER
    proxbox_manufacturer_slug = slugify(proxbox_manufacturer_name)
    proxbox_manufacturer_desc = 'Manufacturer Proxbox will use if none is configured by user in PLUGINS_CONFIG'

    # Check if Proxbox manufacturer already exists.
    proxbox_manufacturer = Manufacturer.objects.filter(name=proxbox_manufacturer_name)

    if proxbox_manufacturer == None:
        try:
            # If Proxbox manufacturer does not exist, create one.
            manufacturer = Manufacturer(
                name=proxbox_manufacturer_name,
                slug=proxbox_manufacturer_slug,
                description=proxbox_manufacturer_desc
            )
            manufacturer.save()
        except:
            return "Error creating the '{0}' manufacturer. Possible errors: the name '{0}' or slug '{1}' is already used.".format(
                proxbox_manufacturer_name, proxbox_manufacturer_slug)

    else:
        manufacturer = proxbox_manufacturer

    return manufacturer
