from .. import (
    create,
)


def tag(netbox_vm, other_tags=None):
    s, netbox_vm = tag(netbox_vm, other_tags)
    return s


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

    customer_tag_name = "Customer"
    customer_tag_slug = "customer"
    customer_observation = "The vm belongs to a customer"
    customer_tag = create.extras.custom_tag(customer_tag_name, customer_tag_slug, customer_observation)

    e1_tag_name = "E1"
    e1_tag_slug = "e1"
    e1_observation = "The vm belongs to Edgeuno"
    e1_tag = create.extras.custom_tag(e1_tag_name, e1_tag_slug, e1_observation)

    first_chars = netbox_vm.name[0:3]

    if first_chars.lower() == 'e1-':
        if customer_tag.id in tags:
            tags.remove(customer_tag.id)
        if e1_tag.id not in tags:
            tags.append(e1_tag.id)
            sve_custom = True
    else:
        if e1_tag.id in tags:
            tags.remove(e1_tag.id)
        if customer_tag.id not in tags:
            tags.append(customer_tag.id)
            sve_custom = True

    if other_tags is not None:
        for t in other_tags:
            try:
                custom_tag_name = t
                custom_tag_slug = not t.replace(" ", "_").lower()
                custom_tag = create.extras.custom_tag(custom_tag_name, custom_tag_slug, t)
                if custom_tag.id not in tags:
                    tags.append(custom_tag.id)
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
