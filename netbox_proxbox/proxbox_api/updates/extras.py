from django.template.defaultfilters import slugify
import re

from ..plugins_config import (
    NETBOX_TENANT_NAME,
    NETBOX_TENANT_REGEX_VALIDATOR,
    NETBOX_TENANT_DESCRIPTION
)

from .. import (
    create,
)


def tag(netbox_vm, other_tags=None):
    s, netbox_vm = tag(netbox_vm, other_tags)
    return s


def validate_custom_tag(name):
    has_string = False
    try:
        rgx = r"" + NETBOX_TENANT_REGEX_VALIDATOR
        matches = re.finditer(rgx, name, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        it.group().lower().strip()
        has_string = True
    except Exception as e:
        print(e)
    return has_string


def base_tag(netbox_vm, other_tags=None):
    output = False
    # Get current tags
    tags = netbox_vm.tags

    # Get tag names from tag objects
    tags_name = []
    for tag in tags:
        tags_name.append(tag.name)

    # If Proxbox not found int Netbox tag's list, update object with the tag.
    sve_custom = False
    if create.extras.tag().name not in tags_name:
        tags.append(create.extras.tag().id)
        # Save new tag to object
        sve_custom = True

    # custom edgeuno tags

    has_string = validate_custom_tag(netbox_vm.name)

    customer_tag_name = "Customer"
    customer_tag_slug = "customer"
    customer_observation = "The vm belongs to a customer"
    customer_tag = create.extras.custom_tag(customer_tag_name, customer_tag_slug, customer_observation)

    if NETBOX_TENANT_NAME is not None:
        e1_tag_name = NETBOX_TENANT_NAME
        e1_tag_slug = slugify(NETBOX_TENANT_NAME)
        e1_observation = NETBOX_TENANT_DESCRIPTION
        e1_tag = create.extras.custom_tag(e1_tag_name, e1_tag_slug, e1_observation)

    if has_string and NETBOX_TENANT_NAME is not None:
        if customer_tag in tags:
            tags.remove(customer_tag)
        if e1_tag not in tags:
            tags.append(e1_tag)
            sve_custom = True
    else:
        if e1_tag in tags:
            tags.remove(e1_tag)
        if customer_tag not in tags:
            tags.append(customer_tag)
            sve_custom = True

    if other_tags is not None:
        for t in other_tags:
            try:
                custom_tag_name = t
                custom_tag_slug = not t.replace(" ", "_").lower()
                custom_tag = create.extras.custom_tag(custom_tag_name, custom_tag_slug, t)
                if custom_tag.id not in tags:
                    tags.append(custom_tag)
                    sve_custom = True
            except Exception as e:
                print(e)

    if sve_custom:
        netbox_vm.tags = tags
        if netbox_vm.save() == True:
            output = True
        else:
            output = False

    return output, netbox_vm
