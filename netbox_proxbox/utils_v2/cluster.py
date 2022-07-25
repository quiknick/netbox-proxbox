try:
    from virtualization.models import Cluster, ClusterType
    from .extras import tag
except Exception as e:
    print(e)
    raise e


#
# virtualization.cluster_types
#
def cluster_type():
    #
    # Cluster Type
    #
    cluster_type_name = 'Proxmox'
    cluster_type_slug = 'proxmox'

    cluster_type_proxbox = ClusterType.objects.get(name=cluster_type_name, slug=cluster_type_slug)

    # If no 'cluster_type' found, create one
    if cluster_type_proxbox == None:

        try:
            cluster_type = ClusterType(
                name=cluster_type_name,
                slug=cluster_type_slug,
                description='Proxmox Virtual Environment. Open-source server management platform'
            )
        except Exception as request_error:
            raise RuntimeError("Error creating the '{0}' cluster type.".format(cluster_type_name)) from request_error

    else:
        cluster_type = cluster_type_proxbox

    return cluster_type


def get_set_cluster(proxmox):
    #
    # Cluster
    #
    # Search cluster name on Proxmox
    proxmox_cluster = proxmox.cluster.status.get()
    proxmox_cluster_name = proxmox_cluster[0].get("name")

    cluster_type_ = cluster_type()

    # Verify if there any cluster created with:
    # Name equal to Proxmox's Cluster name
    # Cluster type equal to 'proxmox'
    cluster_proxbox = Cluster.objects.filter(name=proxmox_cluster_name, type_id=cluster_type_.id).first()

    # If no 'cluster' found, create one using the name from Proxmox
    if cluster_proxbox == None:

        try:
            # Create the cluster with only name and cluster_type

            cluster = Cluster(
                name=proxmox_cluster_name,
                type_id=cluster_type_.id,
                type=cluster_type_,
                tags=[tag().id]
            )
            cluster.save()
        except:
            return "Error creating the '{0}' cluster. Possible errors: the name '{0}' is already used.".format(
                proxmox_cluster_name)

    else:
        cluster = cluster_proxbox

    return cluster
