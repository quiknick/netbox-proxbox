from utilities.choices import ChoiceSet


class TaskTypeChoices(ChoiceSet):
    UNDEFINED = "undefined"
    START_SYNC = "start_sync"
    START_CLUSTER_SYNC = "start_cluster_sync"
    GET_CLUSTER_DATA = "get_cluster_data"
    START_NODE_SYNC = "start_node_sync"
    GET_NODE_IPS = "get_node_ip"
    GET_VMS_FROM_NODES = "get_vms_from_node"
    START_VM_SYNC = "start_vm_sync"
    UPDATE_VM_STATUS = "update_vm_status"
    UPDATE_VM_CUSTOM_FIELDS = "update_vms_custom_fields"
    UPDATE_LOCAL_CONTEXT = "update_local_context"
    UPDATE_VM_RESOURCES = "update_vm_resources"
    UPDATE_VM_TAGS = "update_vm_tags"
    UPDATE_VM_IP = "update_vm_update"
    FINISH_VM_SYNC = "finish_vm_sync"
    CLEAN_NODE_SYNC = "clean_node_sync"
    CLEAN_CLUSTER_SYNC = "clean_cluster_sync"
    CLEAN_SYNC = "clean_sync"
    FINISH_SYNC = "finish_sync"
    REMOVE_UNUSED = "remove_unused"
    REMOVE_UNUSED_STEP2 = "remove_unused_step2"

    CHOICES = (
        (UNDEFINED, "undefined"),
        (START_SYNC, "start_sync"),
        (START_CLUSTER_SYNC, "start_cluster_sync"),
        (GET_CLUSTER_DATA, "get_cluster_data"),
        (START_NODE_SYNC, "start_node_sync"),
        (GET_NODE_IPS, "get_node_ip"),
        (GET_VMS_FROM_NODES, "get_vms_from_node"),
        (START_VM_SYNC, "start_vm_sync"),
        (UPDATE_VM_STATUS, "update_vm_status"),
        (UPDATE_VM_CUSTOM_FIELDS, "update_vms_custom_fields"),
        (UPDATE_LOCAL_CONTEXT, "update_local_context"),
        (UPDATE_VM_RESOURCES, "update_vm_resources"),
        (UPDATE_VM_TAGS, "update_vm_tags"),
        (UPDATE_VM_IP, "update_vm_update"),
        (FINISH_VM_SYNC, "finish_vm_sync"),
        (CLEAN_NODE_SYNC, "clean_node_sync"),
        (CLEAN_CLUSTER_SYNC, "clean_cluster_sync"),
        (CLEAN_SYNC, "clean_sync"),
        (FINISH_SYNC, "finish_sync"),
        (REMOVE_UNUSED, "remove_unused"),
        (REMOVE_UNUSED_STEP2, "remove_unused_step2")
    )


class TaskStatusChoices(ChoiceSet):
    STATUS_UNKNOWN = "unknown"
    STATUS_SCHEDULED = "scheduled"
    STATUS_FAILED = "failed"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_SKIPPED = "skipped"
    STATUS_PAUSE = "pause"

    CHOICES = (
        (STATUS_UNKNOWN, "unknown"),
        (STATUS_SCHEDULED, "scheduled"),
        (STATUS_FAILED, "failed"),
        (STATUS_RUNNING, "running"),
        (STATUS_SUCCEEDED, "succeeded"),
        (STATUS_SKIPPED, "skipped"),
        (STATUS_PAUSE, "pause"),
    )


class RemoveStatusChoices(ChoiceSet):
    NOT_STARTED = "not_started"
    REMOVING = "removing"
    FINISH = "finish"

    CHOICES = (
        (NOT_STARTED, "not_started"),
        (REMOVING, "removing"),
        (FINISH, "finish")
    )
