import pytz
import os

try:
    from django_rq import job

    from .proxbox_api.remove import is_vm_on_proxmox
    from .proxbox_api.update import nodes, vm_full_update

    from .models import SyncTask
    from virtualization.models import VirtualMachine
    from .choices import TaskTypeChoices, TaskStatusChoices, RemoveStatusChoices

    from .others.logger import log

    from .proxbox_api.plugins_config import (
        PROXMOX_SESSIONS as proxmox_sessions,
        QUEUE_NAME,
    )
    from .proxbox_api import (
        updates,
        create,
        remove,
    )
    import uuid
    from datetime import datetime, timedelta

    from .utils_v2.cluster import get_set_cluster
    from .utils_v2.extras import base_tag
    from .utils_v2.nodes import get_set_nodes
    from .utils_v2.util_functions import get_session, get_or_create_sync_job, queue_next_sync, delay_sync, \
        get_cluster_from_domain, custom_delay, should_delay_job_run, nb_search_data_, get_process_vm, set_vm
    from .utils_v2.virtualmachine import get_nb_by_, base_status, base_local_context_data, base_resources, base_add_ip, \
        base_add_configuration, update_vm_role, base_custom_fields
except Exception as e:
    print(e)
    raise e

TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")


# def clear_cluster_vms(children_task):
#     print("***>The cluster process is being Started<***")
#     remove_task = get_or_create_sync_job(None, children_task.user, children_task.remove_unused,
#                                          TaskTypeChoices.REMOVE_UNUSED)
#     remove_task.domain = children_task.domain
#     remove_task.done = False
#     remove_task.parent_id = children_task.id
#     remove_task.cluster_id = children_task.cluster_id
#     remove_task.name = "Remove vms for cluster step 1: " + str(children_task.cluster_id)
#     remove_task.save()
#     children_task.done = False
#     children_task.finish_remove_unused = RemoveStatusChoices.REMOVING
#     children_task.save()
#     current_queue_args = [
#         remove_task.id
#     ]
#
#     queue_next_sync(children_task, remove_unused_step1, current_queue_args, 'remove_unused_step1', None)
#     current_queue_args = [
#         id
#     ]
#     delay_sync(children_task, clean_left, current_queue_args, 1)


def clear_children(children_task):
    parent_id = children_task.parent_id
    if children_task.parent_id is None:
        parent_id = children_task.id

    all_finish = SyncTask.objects.filter(parent_id=parent_id, done=True)

    for el in all_finish:
        try:
            el.delete()
        except Exception as e:
            print(e)
            print("Error: clean_left-2 - {}".format(e))

    if children_task.parent_id:
        try:
            children_task.status = TaskStatusChoices.STATUS_SUCCEEDED
            children_task.done = True
            children_task.save()
        except Exception as e:
            print(e)
        current_queue_args = [
            parent_id
        ]
        queue_next_sync(None, clean_left, current_queue_args, 'clean_left',
                        TaskStatusChoices.STATUS_SUCCEEDED)


def finish_sync(children_task):
    children_task.done = True
    children_task.status = TaskStatusChoices.STATUS_SUCCEEDED
    children_task.end_time = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
    children_task.save()

    sync_task = get_or_create_sync_job(None, children_task.user, children_task.remove_unused)
    if sync_task.job_id is None:
        sync_task.job_id = uuid.uuid4()
        sync_task.save()
    current_queue_args = [
        sync_task.task_id, children_task.user, children_task.remove_unused
    ]
    delay_sync(sync_task, start_sync, current_queue_args, 480)


# @job(QUEUE_NAME)
# def remove_unused_step2(id, nb_vm_each):
#     remove_task_step2 = SyncTask.objects.get(id=id)
#     domain = remove_task_step2.domain
#     proxmox_session = get_session(domain)
#     try:
#         json_vm = {}
#         log = []
#
#         netbox_obj = nb_vm_each
#         netbox_name = netbox_obj.name
#         json_vm["name"] = netbox_name
#
#         # Verify if VM exists on Proxmox
#         vm_on_proxmox = is_vm_on_proxmox(proxmox_session, nb_vm_each)
#
#         if vm_on_proxmox == True:
#             log_message = '[OK] VM exists on both systems (Netbox and Proxmox) -> {}'.format(netbox_name)
#             print(log_message)
#             log.append(log_message)
#
#             json_vm["result"] = False
#
#         # If VM does not exist on Proxmox, delete VM on Netbox.
#         elif vm_on_proxmox == False:
#             log_message = "[WARNING] VM exists on Netbox, but not on Proxmox. Delete it!  -> {}".format(netbox_name)
#             print(log_message)
#             log.append(log_message)
#
#             # Only delete VM that has proxbox tag registered
#             delete_vm = False
#
#             if len(netbox_obj.tags) > 0:
#                 for tag in netbox_obj.tags:
#
#                     if tag.name == 'Proxbox' and tag.slug == 'proxbox':
#
#                         #
#                         # DELETE THE VM/CT
#                         #
#                         # delete_vm = netbox_obj.delete()
#                         print("Delete vm not implemented")
#
#                     else:
#                         log_message = "[ERROR] VM will not be removed because the 'Proxbox' tag was not found. -> {}".format(
#                             netbox_name)
#                         print(log_message)
#                         log.append(log_message)
#
#             elif len(netbox_obj.tags) == 0:
#                 log_message = "[ERROR] VM will not be removed because the 'Proxbox' tag was not found. There is no tag configured.-> {}".format(
#                     netbox_name)
#                 print(log_message)
#                 log.append(log_message)
#
#             if delete_vm == True:
#                 log_message = "[OK] VM successfully removed from Netbox."
#                 print(log_message)
#                 log.append(log_message)
#
#                 json_vm["result"] = True
#
#         else:
#             log_message = '[ERROR] Unexpected error trying to verify if VM exist on Proxmox'
#             print(log_message)
#             log.append(log_message)
#
#             json_vm["result"] = False
#
#         json_vm["log"] = log
#
#         remove_task_step2.done = True
#         remove_task_step2.save()
#
#         current_queue_args = [
#             remove_task_step2.id
#         ]
#         queue_next_sync(remove_task_step2, clean_left, current_queue_args, 'clean_left',
#                         TaskStatusChoices.STATUS_SUCCEEDED)
#
#         return json_vm
#         # json_vm_all.append(json_vm)
#     except Exception as e:
#         print("Error: remove_unused_step2-1 - {}".format(e))
#         print(e)
#         remove_task_step2.done = True
#         remove_task_step2.status = TaskStatusChoices.STATUS_FAILED
#         remove_task_step2.fail_reason = e
#         remove_task_step2.message = e
#         remove_task_step2.save()


# @job(QUEUE_NAME)
# def remove_unused_step1(id):
#     remove_task = SyncTask.objects.get(id=id)
#     try:
#         json_vm_all = []
#
#         # Get all VM/CTs from Netbox
#         netbox_all_vms = VirtualMachine.objects.filter(cluster_id=remove_task.cluster_id)
#         for nb_vm_each in netbox_all_vms:
#             remove_task_step2 = get_or_create_sync_job(None, remove_task.user, remove_task.remove_unused,
#                                                        TaskTypeChoices.REMOVE_UNUSED_STEP2)
#             remove_task_step2.domain = remove_task.domain
#             remove_task_step2.done = False
#             remove_task_step2.parent_id = remove_task.id
#             remove_task_step2.cluster_id = remove_task.cluster_id
#             remove_task_step2.name = "Remove vms for cluster step 1: " + str(remove_task_step2.cluster_id)
#             remove_task_step2.save()
#
#             current_queue_args = [
#                 remove_task_step2.id,
#                 nb_vm_each
#             ]
#             queue_next_sync(remove_task, remove_unused_step2, current_queue_args, 'remove_unused_step2',
#                             TaskStatusChoices.STATUS_RUNNING)
#
#         return json_vm_all
#     except Exception as e:
#         print("Error: remove_unused_step1-1 - {}".format(e))
#         print(e)
#         remove_task.done = True
#         remove_task.status = TaskStatusChoices.STATUS_FAILED
#         remove_task.fail_reason = e
#         remove_task.message = e
#         remove_task.save()
#         queue_next_sync(remove_task, clean_left, current_queue_args, 'clean_left',
#                         TaskStatusChoices.STATUS_SUCCEEDED)


@job(QUEUE_NAME)
def clean_left(item_id):
    print("\n\n***>Processing clean_left<***")
    children_task = None
    try:
        children_task = SyncTask.objects.get(id=item_id)
    except Exception as e:
        print("***>Error Searching for the task it may not being found<***")
        print(e)
    try:
        if children_task is None:
            return
        if children_task.done:
            clear_children(children_task)
            return
        # TODO: There is and error getting the vm's for the cluster
        # if children_task.task_type == TaskTypeChoices.GET_CLUSTER_DATA:
        #     if children_task.remove_unused:
        #         if children_task.finish_remove_unused == RemoveStatusChoices.NOT_STARTED:
        #             clear_cluster_vms(children_task)
        #             return

        all_children = SyncTask.objects.filter(parent_id=children_task.id, done=False)
        if len(all_children) > 0:
            print(f'48. All clusters have not being finish')

            current_queue_args = [
                item_id
            ]
            delay_sync(children_task, clean_left, current_queue_args, 1)

            for elem in all_children:
                try:
                    if not elem.done and (not elem.task_type == TaskTypeChoices.REMOVE_UNUSED) and (
                            not elem.task_type == TaskTypeChoices.REMOVE_UNUSED_STEP2):
                        current_queue_args = [
                            elem.id
                        ]
                        queue_next_sync(children_task, clean_left, current_queue_args, 'clean_left',
                                        TaskStatusChoices.STATUS_PAUSE)
                except Exception as e:
                    print(e)
            return
        else:

            if children_task.parent_id is None:
                if not children_task.done:
                    print(f'FINISHING SYNC')
                    try:
                        finish_sync(children_task)
                    except Exception as e:
                        print(f'Error finishing the sync')
                        print(e)
                    try:
                        clear_children(children_task)
                    except Exception as e:
                        print(f'Error cleaning children')
                        print(e)
                return

            print(f'49. No item left to process')
            children_task.done = True
            children_task.status = TaskStatusChoices.STATUS_SUCCEEDED
            children_task.save()

            clear_children(children_task)
            return

    except Exception as e:
        print("Error: clean_left-1 - {}".format(e))
        print(e)
        children_task.done = True
        children_task.status = TaskStatusChoices.STATUS_FAILED
        children_task.message = e
        children_task.fail_reason = e
        children_task.save()


@job(QUEUE_NAME)
def finish_vm_process(vm_info_task_id):
    print("\n\n***>Processing finish_vm_process<***")
    vm_info_task = get_process_vm(vm_info_task_id)
    vm_info_task.status = TaskStatusChoices.STATUS_SUCCEEDED
    vm_info_task.done = True
    vm_info_task.save()
    # node_task_id = SyncTask.objects.get(id=vm_info_task.parent_id)
    current_queue_args = [
        vm_info_task.id
    ]
    queue_next_sync(vm_info_task, clean_left, current_queue_args, 'clean_left',
                    TaskStatusChoices.STATUS_SUCCEEDED)
    # queue_next_sync(vm_info_task, clean_left, current_queue_args, 'clean_left', TaskStatusChoices.STATUS_SUCCEEDED)
    print("FINISH finish_vm_process")
    # cluster_data = delay_sync(vm_info_task, clean_vms, current_queue_args, 1)


@job(QUEUE_NAME)
def update_vm_process(vm_info_task_id, cluster=None, netbox_vm=None, step='finish'):
    try:
        print("\n\n***>Processing update_vm_process -> {}<***".format(step))
        vm_info_task = get_process_vm(vm_info_task_id)
        proxmox_json = vm_info_task.data_instance
        next_step = 'finish'
        cluster, vmid, node, proxmox_vm_name, proxmox_session, proxmox = nb_search_data_(proxmox_json,
                                                                                         vm_info_task.domain, cluster)

        if netbox_vm is None:
            print("===>Getting vm from db")
            netbox_vm = get_nb_by_(cluster.name, vmid, node, proxmox_vm_name)

        print(f'***>SELECTING OPTION FOR: {step}<***')
        if step == 'status':
            try:
                print("===>Update 'status' field, if necessary.")
                status_updated, netbox_vm = base_status(netbox_vm, proxmox_json)
                print(status_updated)
            except Exception as e:
                print("Error: update_vm_process-status - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.save()
            next_step = 'tags'
        elif step == 'tags':
            print("===>Update tags")
            print(netbox_vm)
            try:
                tag_updated, netbox_vm = base_tag(netbox_vm)
                print(tag_updated)
            except Exception as e:
                print("Error: update_vm_process-tags - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.save()
                # raise e
            next_step = 'custom_fields'
        elif step == 'custom_fields':
            # Update 'local_context_data' json, if necessary.
            try:
                print("===>Update 'custom_fields' field, if necessary.")
                custom_fields_updated, netbox_vm = base_custom_fields(netbox_vm, proxmox_json)
                print(custom_fields_updated)
            except Exception as e:
                print("Error: update_vm_process-custom_fields - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.save()
            next_step = 'local_context'
        elif step == 'local_context':
            # Update 'local_context_data' json, if necessary.
            print("===>Update 'local_context_data' json, if necessary.")
            try:
                PROXMOX = proxmox_session.get('PROXMOX')
                PROXMOX_PORT = proxmox_session.get('PROXMOX_PORT')
                local_context_updated, netbox_vm = base_local_context_data(netbox_vm,
                                                                           proxmox_json,
                                                                           PROXMOX,
                                                                           PROXMOX_PORT)
                print(local_context_updated)
            except Exception as e:
                print("Error: update_vm_process-local_context - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.save()
            next_step = 'resources'
        elif step == 'resources':
            # Update 'resources', like CPU, Memory and Disk, if necessary.
            try:
                print("===>Update 'resources', like CPU, Memory and Disk, if necessary.")
                resources_updated, netbox_vm = base_resources(netbox_vm, proxmox_json)
                print(resources_updated)
            except Exception as e:
                print("Error: update_vm_process-resources - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.save()
            next_step = 'add_ip'
        elif step == 'add_ip':
            print("===>Update ips")
            try:
                ip_update, netbox_vm = base_add_ip(proxmox, netbox_vm, proxmox_json)
                print(ip_update)
            except Exception as e:
                print("Error: update_vm_process-add_ip - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.save()
            next_step = 'add_config'
        elif step == 'add_config':
            print("===>Update configuration")
            try:
                ip_update, netbox_vm = base_add_configuration(proxmox, netbox_vm, proxmox_json)
                print(ip_update)
            except Exception as e:
                print("Error: update_vm_process-add_config - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.save()
            next_step = 'type_role'
        elif step == 'type_role':
            print("===>Update 'type_role' field, if necessary.")
            try:
                status_updated, netbox_vm = update_vm_role(netbox_vm, proxmox_json)
                print(status_updated)
            except Exception as e:
                print("Error: update_vm_process-type_role - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.save()
            next_step = 'finish'

        if step == 'finish':
            print('FINISH ALL PROCESS')
            process_vm_info_args = [vm_info_task.task_id]
            print(f'42. Run the next function (update_vm_status_queue for {vm_info_task_id}) ')
            queue_next_sync(vm_info_task, finish_vm_process, process_vm_info_args, 'finish_vm_process')
        else:
            process_vm_info_args = [vm_info_task.task_id, cluster, netbox_vm, next_step]
            print(f'42. Run the next function (update_vm_status_queue for {vm_info_task_id}) ')
            m = 'update_vm_process_' + next_step
            queue_next_sync(vm_info_task, update_vm_process, process_vm_info_args, m)

        print("FINISH update_vm_status_queue")
    except Exception as e:
        print("Error: update_vm_process-all - {}".format(e))
        print(e)
        return "Error"


@job(QUEUE_NAME)
def process_vm_info2(vm_info_task_id, cluster=None):
    try:
        print("\n\n***>Processing process_vm_info2<***")
        vm_info_task = get_process_vm(vm_info_task_id)
        # proxmox_session = get_session(vm_info_task.domain)
        # proxmox = proxmox_session.get('PROXMOX_SESSION')
        # proxmox_json = vm_info_task.data_instance
        netbox_vm = set_vm(vm_info_task, cluster)
        if cluster is None:
            cluster = get_cluster_from_domain(vm_info_task.domain)
        print("Starting vm update")
        # vm_full_update(proxmox_session, netbox_vm, proxmox_json)
        # print("FINISH process_vm_info2")

        process_vm_info_args = [vm_info_task.task_id, cluster, netbox_vm, 'status']
        print(f'42. Run the next function (update_vm_process for {vm_info_task_id}) ')
        queue_next_sync(vm_info_task, update_vm_process, process_vm_info_args, 'update_vm_process')

    except Exception as e:
        print("Error: update_vm_process-process_vm_info2 - {}".format(e))
        print(e)
        return "Error"


@job(QUEUE_NAME)
def process_vm_info(vm_task_id, proxmox_json, cluster=None, task_id=None):
    print('\n\n***>Executing process_vm_info<***')
    msg = f'[Start VMs data:{vm_task_id}:{task_id}]'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    print(message)

    try:
        vm_task = SyncTask.objects.get(task_id=vm_task_id)
    except Exception as e:
        print("Error: update_vm_process-process_vm_info-vm_task - {}".format(e))
        return 'Error'
    user = vm_task.user
    remove_unused = vm_task.remove_unused
    domain = vm_task.domain
    print('40. Getting or creating the node data sync job')
    vm_info_task = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.START_VM_SYNC)
    if task_id is None or task_id == '':
        task_id = vm_task.task_id

    print('41. Updating info for the cluster data')
    vm_info_task.parent = vm_task
    vm_info_task.parent_id = vm_task.id
    vm_info_task.name = domain + "-" + proxmox_json.get('name')
    vm_info_task.domain = domain
    vm_info_task.status = TaskStatusChoices.STATUS_RUNNING
    vm_info_task.data_instance = proxmox_json
    vm_info_task.cluster_id = vm_task.cluster_id
    vm_info_task.job_id = vm_task.job_id
    vm_info_task.save()
    if cluster is None:
        cluster = get_cluster_from_domain(domain)

    process_vm_info_args = [vm_info_task.task_id, cluster]

    print(f'42. Run the next function (process_vm_info2 for {vm_info_task.task_id}) ')
    print(process_vm_info_args)
    queue_next_sync(vm_info_task, process_vm_info2, process_vm_info_args, 'process_vm_info2')

    print("43. FINISH process_vm_info")


@job(QUEUE_NAME)
def get_vms_for_the_node(node_task_id, task_id, iteration=0):
    print('\n\n***>Executing get_vms_for_the_node<***')
    msg = f'[Start VMs data:{node_task_id}:{task_id}] iteration: {iteration}'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    print(message)
    if iteration > 3:
        return f'Canceling the job'

    try:
        node_task = SyncTask.objects.get(task_id=node_task_id)
    except Exception as e:
        print("Error: update_vm_process-get_vms_for_the_node - {}".format(e))
        print(e)
        print('SYNC JOB NOT FOUND DELAYING IN ORDER TO WAIT FOR THE DATA BASE COMMIT')
        print(e)
        iteration = iteration + 1
        current_queue_args = [
            node_task_id, task_id, iteration
        ]
        custom_delay(get_vms_for_the_node, current_queue_args, None, 500)
        return f'Delaying the job'
    user = node_task.user
    remove_unused = node_task.remove_unused
    domain = node_task.domain

    print('35. Getting or creating the node data sync job')
    vm_task = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.GET_VMS_FROM_NODES)

    if task_id is None or task_id == '':
        task_id = vm_task.task_id
    print('36. Updating info for the cluster data')
    vm_task.parent = node_task
    vm_task.parent_id = node_task.id
    vm_task.name = 'Getting vms'
    vm_task.domain = domain
    vm_task.status = TaskStatusChoices.STATUS_RUNNING
    vm_task.cluster_id = node_task.cluster_id
    vm_task.job_id = node_task.job_id
    vm_task.save()

    try:
        proxmox_session = get_session(domain)
        proxmox = proxmox_session.get('PROXMOX_SESSION')
    except Exception as e:
        print("Error: update_vm_process-get_vms_for_the_node-proxmox - {}".format(e))
        print(e)

    #
    # VIRTUAL MACHINES / CONTAINERS
    #
    print('\n\n\nVIRTUAL MACHINES...')
    virtualmachines_list = []
    should_delay = should_delay_job_run(vm_task, TaskTypeChoices.GET_VMS_FROM_NODES, domain)
    print(f'37. Should delay the job {should_delay}')
    if should_delay:
        current_queue_args = [
            node_task_id, task_id, 0
        ]
        # Run the delay process if there is already other process with the same characterics is running
        print('38. Run the delay process if there is already other process with the same characterics is running')
        cluster_nodes = delay_sync(vm_task, start_cluster_sync, current_queue_args, 1)
        return f'Delaying :{cluster_nodes.name}:{cluster_nodes.task_id}'
    else:
        print('\nUPDATE ALL...')
        # Get all VM/CTs from Proxmox
        node_vms_all = proxmox.cluster.resources.get(type='vm')
        cluster = get_set_cluster(proxmox)
        vm_task.data_instance = node_vms_all
        vm_task.save()
        counter = 0
        for px_vm_each in node_vms_all:
            try:
                # if counter > 0:
                #     break
                # if not (px_vm_each['name'] == 'ATRO-001-BOG' or px_vm_each['name'] == 'E1-0.co.ntp.edgeuno.com' or
                #         px_vm_each['name'] == 'colombiabridge'):
                #     continue
                # if not (px_vm_each['name'] == 'E1-kali-sofia'):
                #     continue
                print(px_vm_each)
                is_template = px_vm_each.get("template")
                if is_template == 1:
                    continue
                process_vm_info_args = [
                    vm_task.task_id, px_vm_each, cluster, None
                ]

                print(f'34. Run the next function (process_vm_info for {domain}) ')
                print(process_vm_info_args)
                counter = counter + 1
                queue_next_sync(vm_task, process_vm_info, process_vm_info_args, 'process_vm_info')

                # vm_updated = virtual_machine(proxmox_json=px_vm_each, proxmox_session=proxmox_session, cluster=cluster)
                # virtualmachines_list.append(vm_updated)
            except Exception as e:
                print("Error: update_vm_process-px_vm_each-proxmox - {}".format(e))
                print(e)


@job(QUEUE_NAME)
def get_nodes_for_the_cluster(cluster_data_id, task_id, iteration=0):
    print('\n\n***>Executing get_nodes_for_the_cluster<***')
    msg = f'[Start nodes data:{cluster_data_id}:{task_id}] iteration: {iteration}'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    print(message)
    if iteration > 3:
        return f'Canceling the job'
    try:
        cluster_data = SyncTask.objects.get(task_id=cluster_data_id)
    except Exception as e:
        print("Error: update_vm_process-get_nodes_for_the_cluster - {}".format(e))
        print(e)
        print('SYNC JOB NOT FOUND DELAYING IN ORDER TO WAIT FOR THE DATA BASE COMMIT')
        print(e)
        iteration = iteration + 1
        current_queue_args = [
            cluster_data_id, task_id, iteration
        ]
        custom_delay(get_nodes_for_the_cluster, current_queue_args, None, 500)
        return f'Delaying the job'
    user = cluster_data.user
    remove_unused = cluster_data.remove_unused
    domain = cluster_data.domain

    print('29. Getting or creating the node data sync job')
    cluster_nodes = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.START_NODE_SYNC)

    if task_id is None or task_id == '':
        task_id = cluster_data.task_id
    print('30. Updating info for the cluster data')
    cluster_nodes.parent = cluster_data
    cluster_nodes.parent_id = cluster_data.id
    cluster_nodes.name = 'Start cluster nodes'
    cluster_nodes.domain = domain
    cluster_nodes.status = TaskStatusChoices.STATUS_RUNNING
    cluster_nodes.cluster_id = cluster_data.cluster_id
    cluster_nodes.job_id = cluster_data.job_id
    cluster_nodes.save()

    cluster_all = cluster_data.data_instance
    proxmox_cluster = cluster_all[0]
    #
    # NODES
    #
    print('\n\n\nNODES...')
    nodes_list = []
    node_response_list = []
    proxmox_nodes = cluster_all[1:]

    print('Finish get_cluster_data')
    should_delay = should_delay_job_run(cluster_nodes, TaskTypeChoices.START_NODE_SYNC, domain)
    print(f'31. Should delay the job {should_delay}')
    if should_delay:
        current_queue_args = [
            cluster_data_id, task_id, 0
        ]
        # Run the delay process if there is already other process with the same characterics is running
        print('32. Run the delay process if there is already other process with the same characterics is running')
        cluster_nodes = delay_sync(cluster_nodes, start_cluster_sync, current_queue_args, 1)
        return f'Delaying :{cluster_nodes.name}:{cluster_nodes.task_id}'
    else:
        # Run the next function (start_cluster_sync)
        cluster_nodes_id = cluster_nodes.task_id
        # Get all NODES from Proxmox
        try:
            proxmox_session = get_session(domain)
            proxmox = proxmox_session.get('PROXMOX_SESSION')
        except Exception as e:
            print("Error: update_vm_process-get_nodes_for_the_cluster-proxmox_session - {}".format(e))
            print(e)

        for px_node_each in proxmox_nodes:
            try:
                print('Nodes...')
                print(px_node_each)
                node_updated = get_set_nodes(
                    proxmox_json=px_node_each,
                    proxmox_cluster=proxmox_cluster,
                    proxmox=proxmox,
                    proxmox_session=proxmox_session
                )
                node_response_list.append(px_node_each)
                print(px_node_each)
            except Exception as e:
                print("Error: get_nodes_for_the_cluster-px_node_each {}".format(e))
                message = "OS error: {0}".format(e)
                print(message)
                log.error(e)

        cluster_nodes.data_instance = node_response_list
        cluster_nodes.save()
        print(f'33. Finish get_nodes_for_the_cluster')

        get_nodes_for_the_cluster_args = [
            cluster_nodes_id, None, 0
        ]
        print(f'34. Run the next function (get_nodes_for_the_cluster for {domain}) ')
        queue_next_sync(cluster_nodes, get_vms_for_the_node, get_nodes_for_the_cluster_args,
                        'get_vms_for_the_node')


@job(QUEUE_NAME)
def get_cluster_data(cluster_task_id, domain, task_id, iteration=0):
    print('\n\n***>Executing get_cluster_data<***')
    try:
        msg = f'[Start getting cluster data:{cluster_task_id}:{domain}:{task_id}] iteration: {iteration}'
        message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
        log.info(message)
        print(message)
        if iteration > 3:
            return f'Canceling the job'

        try:
            cluster_sync = SyncTask.objects.get(task_id=cluster_task_id)
        except Exception as e:
            print("Error: get_cluster_data-cluster {}".format(e))
            print(e)
            print('SYNC JOB NOT FOUND DELAYING IN ORDER TO WAIT FOR THE DATA BASE COMMIT')
            print(e)
            iteration = iteration + 1
            current_queue_args = [
                cluster_task_id,
                domain,
                task_id,
                iteration
            ]
            custom_delay(get_cluster_data, current_queue_args, None, 500)
            return f'Delaying the job'
        user = cluster_sync.user
        remove_unused = cluster_sync.remove_unused

        print('22. Getting or creating the cluster data sync job')
        cluster_data = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.GET_CLUSTER_DATA)

        if task_id is None or task_id == '':
            task_id = cluster_data.task_id

        print('24. Updating info for the cluster data')
        cluster_data.parent = cluster_sync
        cluster_data.parent_id = cluster_sync.id
        cluster_data.name = 'Start cluster data'
        cluster_data.domain = domain
        cluster_data.status = TaskStatusChoices.STATUS_RUNNING
        cluster_data.job_id = cluster_sync.job_id
        cluster_data.save()
        print('25. Getting proxmox session')
        proxmox_session = get_session(domain)
        proxmox = proxmox_session.get('PROXMOX_SESSION')
        cluster_all = proxmox.cluster.status.get()
        print(cluster_all)
        cluster_data.data_instance = cluster_all
        cluster_data.save()
        cluster = get_set_cluster(proxmox)
        cluster_data.cluster_id = cluster.id
        cluster_data.save()
        print('\n\n\nCLUSTER...')
        print('[OK] CLUSTER created. -> {}'.format(cluster.name))

        proxmox_cluster = cluster_all[0]
        print(proxmox_cluster)
        print('Finish get_cluster_data')
        should_delay = should_delay_job_run(cluster_data, TaskTypeChoices.GET_CLUSTER_DATA, domain)
        print(f'26. Should delay the job {should_delay}')
        if should_delay:
            current_queue_args = [
                cluster_task_id, domain, task_id, 0
            ]
            # Run the delay process if there is already other process with the same characterics is running
            print('27. Run the delay process if there is already other process with the same characterics is running')
            cluster_data = delay_sync(cluster_data, start_cluster_sync, current_queue_args, 1)
            return f'Delaying :{cluster_data.name}:{cluster_data.task_id}'
        else:
            # Run the next function (start_cluster_sync)

            cluster_data_id = cluster_data.task_id
            get_nodes_for_the_cluster_args = [
                cluster_data_id, None, 0
            ]
            print(f'28. Run the next function (get_nodes_for_the_cluster for {domain}) ')
            queue_next_sync(cluster_data, get_nodes_for_the_cluster, get_nodes_for_the_cluster_args,
                            'get_nodes_for_the_cluster')

        return f'Finish...'

    except Exception as e:
        print("Error: get_cluster_data-cluster-all {}".format(e))
        print(e)
        return f'Error'


@job(QUEUE_NAME)
def start_cluster_sync(sync_job_id, task_id, iteration=0):
    try:
        print('\n\n***>Executing start_cluster_sync<***')
        if iteration > 3:
            return f'Canceling the job'
        msg = f'[Start cluster sync:{sync_job_id}] - iteration: {iteration}'
        message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
        log.info(message)
        print(message)
        try:
            sync_job = SyncTask.objects.get(task_id=sync_job_id)
        except Exception as e:
            print("Error: start_cluster_sync-sync_job {}".format(e))
            print('SYNC JOB NOT FOUN DELAYING IN ORDER TO WAIT FOR THE DATA BASE COMMIT')
            print(e)
            iteration = iteration + 1
            current_queue_args = [
                sync_job_id,
                task_id,
                iteration
            ]
            custom_delay(start_cluster_sync, current_queue_args, None, 500)
            return f'Delaying the job'
        user = sync_job.user
        remove_unused = sync_job.remove_unused
        cluster_sync = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.START_CLUSTER_SYNC)
        if task_id is None or task_id == '':
            task_id = cluster_sync.task_id
        print('18. Set parent for the cluster job')
        cluster_sync.parent = sync_job
        cluster_sync.parent_id = sync_job.id
        cluster_sync.name = 'Start cluster sync'
        cluster_sync.job_id = sync_job.job_id
        cluster_sync.save()

        should_delay = should_delay_job_run(cluster_sync, TaskTypeChoices.START_CLUSTER_SYNC, None)
        print(f'19. Should delay the job {should_delay}')
        if should_delay:
            current_queue_args = [
                sync_job_id,
                task_id,
                0
            ]
            # Run the delay process if there is already other process with the same characterics is running
            print('20. Run the delay process if there is already other process with the same characterics is running')
            cluster_sync = delay_sync(cluster_sync, start_cluster_sync, current_queue_args, 1)
            return f'Delaying :{cluster_sync.name}:{cluster_sync.task_id}'
        else:
            # Run the next function (start_cluster_sync)
            for key in proxmox_sessions:
                try:
                    session = proxmox_sessions[key]
                    domain = session['PROXMOX']
                    cluster_task_id = cluster_sync.task_id
                    get_cluster_data_args = [
                        cluster_task_id,
                        domain,
                        None,
                        0
                    ]
                    print(f'21. Run the next function (get_cluster_data for {domain}) ')
                    queue_next_sync(cluster_sync, get_cluster_data, get_cluster_data_args, 'get_cluster_data')
                except Exception as e:
                    print("Error: start_cluster_sync-proxmox_sessions {}".format(e))
                    message = "OS error: {0}".format(e)
                    print(message)
                    log.error(e)
            return f'Finish:{cluster_sync.name}:{cluster_sync.task_id}'
    except Exception as e:
        print("Error: start_cluster_sync-all-1 {}".format(e))
        print(e)
        return f'Error'


def job_start_sync(task_id, user, remove_unused):
    print('\n\n***>Executing job_start_sync<***')
    print('1. Start job_start_sync function')
    sync_task = get_or_create_sync_job(task_id, user, remove_unused)
    if sync_task.job_id is None:
        sync_task.job_id = uuid.uuid4()
        sync_task.save()
    if task_id is None or task_id == '':
        task_id = sync_task.task_id

    should_delay = should_delay_job_run(sync_task, TaskTypeChoices.START_SYNC, None)
    print(f'8. Should delay the job {should_delay}')
    if should_delay:
        current_running = SyncTask.objects.filter(
            task_type=TaskTypeChoices.START_SYNC,
            done=False,
            status=TaskStatusChoices.STATUS_RUNNING
        ).first()

        all_children_list = SyncTask.objects.filter(parent_id=current_running.id, done=False)
        all_children = len(all_children_list)

        if all_children < 1:
            current_running.done = True
            current_running.status = TaskStatusChoices.STATUS_FAILED
            current_running.save()
            current_running = None

        try:
            if current_running is not None and not (current_running.id == sync_task.id):
                ctm = datetime.now().replace(microsecond=0, tzinfo=pytz.utc)
                ct = ctm.timestamp()
                st = current_running.start_time if current_running.start_time is not None else current_running.timestamp
                t = st.replace(microsecond=0, tzinfo=pytz.utc).timestamp()
                r = (t - ct)
                r = abs(r)

                if r > 21600:
                    current_running.done = True
                    current_running.status = TaskStatusChoices.STATUS_FAILED
                    current_running.save()

                    if all_children > 0:
                        current_queue_args = [
                            current_running.id
                        ]
                        queue_next_sync(current_running, clean_left, current_queue_args, 'clean_left',
                                        TaskStatusChoices.STATUS_SUCCEEDED)


        except Exception as e:
            print(e)

        current_queue_args = [
            task_id,
            user,
            remove_unused
        ]
        # Run the delay process if there is already other process with the same characterics is running
        print('9. Run the delay process if there is already other process with the same characterics is running')
        sync_task = delay_sync(sync_task, start_sync, current_queue_args, 1)
    else:
        next_queue_args = [
            task_id,
            None,
            0
        ]
        # Run the next function (start_cluster_sync)
        print('14. Run the next function (start_cluster_sync) ')
        sync_task.start_time = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
        sync_task.save()
        sync_task = queue_next_sync(sync_task, start_cluster_sync, next_queue_args, 'start_cluster_sync')
    return sync_task


@job(QUEUE_NAME)
def start_sync(task_id, user, remove_unused=True):
    print('\n\n***>Executing start_sync<***')
    msg = '[Proxbox - Netbox plugin | Update All | queue]'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    print(message)
    sync_task = job_start_sync(task_id, user, True)
    print('Finish start_sync')
    if sync_task is None:
        return f'No sync task created'
    else:
        return f'Finish:{sync_task.name}:{sync_task.task_id}'
