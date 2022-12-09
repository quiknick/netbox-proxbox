import pytz
import os
import math

from .others.db import namedtuplefetchall
from .utils_v2.proxbox import set_get_proxbox_item, set_get_proxbox_item_basic, set_get_proxbox_from_vm

try:
    from django_rq import job
    from django.db import connection, transaction

    from .proxbox_api.remove import is_vm_on_proxmox
    from .proxbox_api.update import nodes, vm_full_update

    from .models import SyncTask, ProxmoxVM
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
    from .utils_v2.extras import base_tag, tag
    from .utils_v2.nodes import get_set_nodes
    from .utils_v2.util_functions import get_session, get_or_create_sync_job, queue_next_sync, delay_sync, \
        get_cluster_from_domain, custom_delay, should_delay_job_run, nb_search_data_, get_process_vm, set_vm
    from .utils_v2.virtualmachine import get_nb_by_, base_status, base_local_context_data, base_resources, base_add_ip, \
        base_add_configuration, update_vm_role, base_custom_fields
except Exception as e:
    print(e)
    raise e

TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")


def update_children_sql(parent_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE netbox_proxbox_synctask SET done = true WHERE parent_id = %s", [parent_id])
        return True
    except Exception as e:
        print(e)
        print("Error: update_children_sql - {}".format(e))
        return False


def update_finish_sql(job_id, preserve):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE netbox_proxbox_synctask SET done = true WHERE job_id = %s AND id != %s",
                           [job_id, preserve])
        return True
    except Exception as e:
        print(e)
        print("Error: update_children_sql - {}".format(e))
        return False


def delete_unused_sql(job_id, preserve):
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE from netbox_proxbox_synctask where job_id = %s and id != %s AND (fail_reason = '' OR fail_reason is null)",
                [job_id, preserve])
        return True
    except Exception as e:
        print(e)
        print("Error: update_children_sql - {}".format(e))
        return False


def delete_proxbox_vm_sql(proxbox_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE from netbox_proxbox_proxmoxvm where id = %s ",
                           [proxbox_id])
        return True
    except Exception as e:
        print(e)
        print("Error: delete_proxbox_vm_sql - {}".format(e))
        return False


def get_total_count(job_id):
    try:
        with connection.cursor() as cursor:
            query_count = '''
                select count(*) as count
                from virtualization_virtualmachine as vv
                where id not in
                (select virtual_machine_id
                    from netbox_proxbox_proxmoxvm npv
                    where npv.latest_job = %s)
                '''
            cursor.execute(query_count, [job_id])
            results = namedtuplefetchall(cursor)
            count = results[0].count
            # total_pages = math.ceil(count / limit)
            return count

    except Exception as e:
        print(e)
        print("Error: get_total_pages - {}".format(e))
        return 0


def get_vm_to_delete(job_id, page, limit=100):
    try:
        offset = (page - 1) * limit
        query_count = '''
                select *
                from virtualization_virtualmachine as vv
                where id not in
                      (select virtual_machine_id
                       from netbox_proxbox_proxmoxvm npv
                       where npv.latest_job = '{}')
                limit {} offset {}
                '''.format(job_id, limit, offset)
        return VirtualMachine.objects.raw(query_count)
    except Exception as e:
        print(e)
        print("Error: get_vm_to_delete - {}".format(e))
        return None


def clear_children(children_task):
    parent_id = children_task.id
    update_children_sql(parent_id)
    return


def finish_sync(queue_task):
    # Mark the task as done, succeses and set the end_time
    queue_task.done = True
    queue_task.status = TaskStatusChoices.STATUS_SUCCEEDED
    queue_task.end_time = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
    queue_task.save()

    # Clean the table deleting all other rows that are no longer needed
    delete_unused_sql(queue_task.job_id, queue_task.id)

    # Create a new sync job that is going to run 8 hours later
    sync_task = get_or_create_sync_job(None, queue_task.user, queue_task.remove_unused)

    # Setting the job id for the next execution
    if sync_task.job_id is None:
        sync_task.job_id = uuid.uuid4()
        sync_task.status = TaskStatusChoices.STATUS_SCHEDULED
        sync_task.save()

    # Start the next process execution
    current_queue_args = [
        sync_task.id, queue_task.user, queue_task.remove_unused
    ]
    delay_sync(sync_task, start_sync, current_queue_args, 480)
    print("SYNCRINIZATION FINISH {}".format(sync_task.job_id))
    return True


def get_promox_config(vm):
    config = None
    proxbox_vm = None
    domain = None
    node = None
    vmid = None
    type = None
    try:
        proxbox_vm = ProxmoxVM.objects.filter(virtual_machine_id=vm.id).first()
        if proxbox_vm:
            # If there is an item get the configuration from proxmox
            domain = proxbox_vm.domain
            node = proxbox_vm.node
            vmid = proxbox_vm.proxmox_vm_id
            type = proxbox_vm.type

        # Get the domain from the context data of the vm if no proxbox item exist
        if domain is None:
            domain = vm.local_context_data['proxmox'].get('domain')
        if node is None:
            node = vm.local_context_data['proxmox'].get('node')
        if vmid is None:
            vmid = vm.local_context_data['proxmox'].get('id')
        if type is None:
            type = vm.local_context_data['proxmox'].get('type')

        if domain is not None:
            proxmox_session = get_session(domain)
            proxmox = proxmox_session.get('PROXMOX_SESSION')

        if proxmox is not None and node is not None and vmid is not None:
            if type == 'qemu':
                config = proxmox.nodes(node).qemu(vmid).config.get()
            if type == 'lxc':
                config = proxmox.nodes(node).lxc(vmid).config.get()
    except Exception as e:
        print("Error: get_promox_config-1 - {}".format(e))
        print(e)
        config = None
    return config, proxbox_vm, domain, node, vmid, type


def get_tags_name(vm):
    tags = vm.tags.all()
    tags_name = []
    tg = tag()
    for c_tag in tags:
        tags_name.append(c_tag.name)

    return tags_name, tg


def full_vm_delete(vm, proxbox_vm):
    try:
        if proxbox_vm:
            st = SyncTask.objects.filter(proxmox_vm_id=proxbox_vm.id).first()
            if st:
                try:
                    st.proxmox_vm_id = None
                    st.proxmox_vm = None
                    st.virtual_machine_id = None
                    st.virtual_machine = None
                    st.save()
                except Exception as e:
                    print(f'[ERROR] Deleting the sync task')
                    print(e)
            try:
                with transaction.atomic():
                    proxbox_vm.virtual_machine_id = None
                    proxbox_vm.cluster_id = None
                    proxbox_vm.device_id = None
                    proxbox_vm.save()
                    delete_proxbox_vm_sql(proxbox_vm.id)
            except Exception as e:
                print(f'[ERROR] The proxbox vm/ct')
                print(e)
        with transaction.atomic():
            r = vm.delete()  # VirtualMachine.objects.filter(id=vm.id).delete()
            print(f'[OK] DELETED')
            print(r)
    except Exception as e:
        print(f'[ERROR] Deleting vm - 1 ')
        print(e)
    finally:
        return True


@job(QUEUE_NAME)
def delete_vm(vm_id, remove_task_id):
    # Get the task and the vm from the database
    vm = VirtualMachine.objects.filter(id=vm_id).first()
    remove_task = SyncTask.objects.filter(id=remove_task_id).first()
    try:
        # If there is no task then do nothing
        if remove_task is None:
            return

        if vm:
            # Get the configuration from the proxbox table
            config, proxbox_vm, domain, node, vmid, type = get_promox_config(vm)
            tags_name, tg = get_tags_name(vm)
            if tg.name in tags_name:
                if config is None:
                    full_vm_delete(vm, proxbox_vm)
                elif proxbox_vm is None:
                    proxmox_session = get_session(domain)
                    proxmox = proxmox_session.get('PROXMOX_SESSION')
                    cluster = get_set_cluster(proxmox)
                    proxbox_vm = set_get_proxbox_from_vm(vm, domain, node, vmid, remove_task.job_id, cluster, type,
                                                         config)
    except Exception as e:
        print(f'[ERROR] Deleting vm')
        print(e)
    finally:
        if remove_task:
            remove_task.done = True
            remove_task.status = TaskStatusChoices.STATUS_SUCCEEDED
            remove_task.save()


@job(QUEUE_NAME)
def finish_await(sync_task_process_id, await_for=1):
    print("\n\n***>Processing finish_await for {}<***".format(sync_task_process_id))
    # Get the last sync task
    queue_task = SyncTask.objects.filter(id=sync_task_process_id).first()
    # if there is no task or the task is mark as done then do nothing
    if queue_task is None:
        return
    if queue_task.done:
        return

    # Monitor if the job has finish, if not then wait a minute and try again
    all_children = SyncTask.objects \
        .filter(job_id=queue_task.job_id, done=False, task_type=TaskTypeChoices.REMOVE_UNUSED) \
        .exclude(id=queue_task.id).count()
    if all_children > 0:
        current_queue_args = [queue_task.id]
        delay_sync(queue_task, finish_await, current_queue_args, await_for)
        return

    return finish_sync(queue_task)


@job(QUEUE_NAME)
def start_removing_vms(sync_task_process_id):
    # Get the last sync task
    queue_task = SyncTask.objects.filter(id=sync_task_process_id).first()
    # if there is no task or the task is mark as done then do nothing
    if queue_task is None:
        return
    if queue_task.done:
        return
    # Mark the task removing unused as removing and set the done as false just in case
    queue_task.finish_remove_unused = RemoveStatusChoices.REMOVING
    queue_task.done = False
    queue_task.save()

    # Mark all the children job task as done, just in case there were not mark

    update_finish_sql(queue_task.job_id, queue_task.id)

    # Get all the vm's to be deleted
    limit = 100
    count = get_total_count(queue_task.job_id)
    # if there are no task just finish the process
    if count < 1:
        queue_task.finish_remove_unused = RemoveStatusChoices.FINISH
        queue_task.save()
        finish_sync(queue_task)
        return

    # Get the number of pages base on the limit
    pages = math.ceil(count / limit)
    for n in range(pages):
        if n + 1 > pages:
            break
        # Get the vms to be deleted
        results = get_vm_to_delete(queue_task.job_id, n + 1, limit)
        for vm in results:
            # for each vm call another function in to the queue in order to complete the deletion of the vm
            remove_task_step = get_or_create_sync_job(None, queue_task.user, queue_task.remove_unused,
                                                      TaskTypeChoices.REMOVE_UNUSED)
            remove_task_step.domain = queue_task.domain
            remove_task_step.done = False
            remove_task_step.parent_id = queue_task.id
            remove_task_step.job_id = queue_task.job_id
            remove_task_step.name = "Remove vms : " + str(vm.name)
            remove_task_step.save()

            # Start the queue for finishing the vm
            current_queue_args = [vm.id, remove_task_step.id]
            queue_next_sync(None, delete_vm, current_queue_args, ' delete_vm ', TaskStatusChoices.STATUS_SUCCEEDED)

    # Start the queue that awaits the for the deletions to finish
    current_queue_args = [queue_task.id]
    delay_sync(queue_task, finish_await, current_queue_args, 1)
    return


@job(QUEUE_NAME)
def clean_left(item_id):
    # print("\n\n***>Processing clean_left for {}<***".format(item_id))
    queue_task = SyncTask.objects.filter(id=item_id).first()

    try:
        # If the task doesn't exist remove
        if queue_task is None:
            return
        # If the item has already being called then don't do anything
        if queue_task.finish_remove_unused == RemoveStatusChoices.FINISH:
            return
            # If the queue is already done, and if it  has no parent id just call is father and see what happens :)
        if queue_task.done and queue_task.parent_id is not None:
            current_queue_args = [
                queue_task.parent_id
            ]
            queue_next_sync(None, clean_left, current_queue_args, 'clean_left',
                            TaskStatusChoices.STATUS_SUCCEEDED)
            return

        # Get all children that are not finish
        all_children = SyncTask.objects.filter(parent_id=queue_task.id, done=False)
        if len(all_children) > 0:
            # If not finish just wait until it finish, we are going to trust that none of the other process
            current_queue_args = [
                item_id
            ]
            delay_sync(queue_task, clean_left, current_queue_args, 1)

            return

        # If the parent is none then we start with the cleaning process
        if queue_task.parent_id is None:
            if queue_task.finish_remove_unused == RemoveStatusChoices.NOT_STARTED:
                queue_task.finish_remove_unused = RemoveStatusChoices.REMOVING
                queue_task.save()
                current_queue_args = [
                    item_id
                ]
                # delay_sync(queue_task, start_removing_vms, current_queue_args, 1)
                queue_next_sync(None, start_removing_vms, current_queue_args, 'start_removing_vms',
                                TaskStatusChoices.STATUS_SUCCEEDED)
            return

        # If the item  has no children then mark the item as completed
        print('[OK] {} has no children, continue with the father'.format(queue_task.name))
        queue_task.done = True
        queue_task.status = TaskStatusChoices.STATUS_SUCCEEDED
        queue_task.finish_remove_unused = RemoveStatusChoices.FINISH
        queue_task.save()

        # Clear all its children
        clear_children(queue_task)
        # Call it's parent
        current_queue_args = [
            queue_task.parent_id
        ]
        queue_next_sync(None, clean_left, current_queue_args, 'clean_left',
                        TaskStatusChoices.STATUS_SUCCEEDED)
        return

    except Exception as e:
        print("\n\n***>Processing clean_left for {}<***".format(item_id))
        print("[ERROR] clean_left-1 - {}".format(e))
        print(e)
        if queue_task:
            queue_task.done = True
            queue_task.status = TaskStatusChoices.STATUS_FAILED
            queue_task.message = e
            queue_task.fail_reason = e
            queue_task.save()
            current_queue_args = [
                queue_task.parent_id
            ]
            queue_next_sync(None, clean_left, current_queue_args, 'clean_left',
                            TaskStatusChoices.STATUS_SUCCEEDED)
        return


@job(QUEUE_NAME)
def finish_vm_process(vm_info_task_id):
    # print("\n\n***>Processing finish_vm_process<***")
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
    print("[OK] FINISH finish_vm_process")
    # cluster_data = delay_sync(vm_info_task, clean_vms, current_queue_args, 1)


@job(QUEUE_NAME)
def update_vm_process(vm_info_task_id, cluster=None, proxbox_vm=None, step='finish'):
    try:
        # print("\n\n***>Processing update_vm_process -> {}<***".format(step))
        vm_info_task = get_process_vm(vm_info_task_id)
        proxmox_json = vm_info_task.data_instance
        next_step = 'finish'
        domain = vm_info_task.domain
        cluster, vmid, node, proxmox_vm_name, proxmox_session, proxmox = nb_search_data_(proxmox_json,
                                                                                         domain, cluster)

        if proxbox_vm is None:
            return
        netbox_vm = proxbox_vm.virtual_machine
        # print(f'***>SELECTING OPTION FOR: {step}<***')
        if step == 'status' or step == 'tags' or step == 'custom_fields' or step == 'local_context' or step == 'resources':

            status_updated, netbox_vm = base_status(netbox_vm, proxmox_json)
            # print("===>Update tags")
            # print(netbox_vm)
            tag_updated, netbox_vm = base_tag(netbox_vm)
            # print(tag_updated)
            # print("===>Update 'custom_fields' field, if necessary.")
            custom_fields_updated, netbox_vm = base_custom_fields(netbox_vm, proxmox_json)
            # print(custom_fields_updated)
            # Update 'local_context_data' json, if necessary.
            # print("===>Update 'local_context_data' json, if necessary.")
            PROXMOX = proxmox_session.get('PROXMOX')
            PROXMOX_PORT = proxmox_session.get('PROXMOX_PORT')
            local_context_updated, netbox_vm = base_local_context_data(netbox_vm,
                                                                       proxmox_json,
                                                                       PROXMOX,
                                                                       PROXMOX_PORT,
                                                                       vm_info_task.domain)
            # print(local_context_updated)
            # print("===>Update 'resources', like CPU, Memory and Disk, if necessary.")
            resources_updated, netbox_vm = base_resources(netbox_vm, proxmox_json)
            # print(resources_updated)
            netbox_vm.save()
            # print("[OK] Updated 'status', 'tags', 'custom_fields', 'local_context_data', 'resources' for: {}-{}".format(
            #     netbox_vm.name, netbox_vm.id))
            next_step = 'add_config'
        elif step == 'add_config':
            # print("===>Update configuration")
            try:
                add_config, netbox_vm = base_add_configuration(proxmox, netbox_vm, proxmox_json)
                netbox_vm.save()
                # print(add_config)
            except Exception as e:
                print("Error: update_vm_process-add_config - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.fail_reason = "{}==>{}".format(step, e)
                vm_info_task.save()
            # print("[OK] Updated 'configuration' for: {}-{}".format(netbox_vm.name, netbox_vm.id))
            next_step = 'type_role'
        elif step == 'type_role':
            # print("===>Update 'type_role' field, if necessary.")
            try:
                status_updated, netbox_vm = update_vm_role(netbox_vm, proxmox_json)
                netbox_vm.save()
                # print("[OK] Updated 'type_role' for: {}-{}".format(netbox_vm.name, netbox_vm.id))
                # print(status_updated)
            except Exception as e:
                print("Error: update_vm_process-type_role - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.fail_reason = "{}==>{}".format(step, e)
                vm_info_task.save()
            next_step = 'add_ip'
        elif step == 'add_ip':
            # print("===>Update ips")
            try:
                ip_update, netbox_vm = base_add_ip(proxmox, netbox_vm, proxmox_json)
                # print("[OK] Updated 'ip' for: {}-{}".format(netbox_vm.name, netbox_vm.id))
            except Exception as e:
                print("Error: update_vm_process-add_ip - {}".format(e))
                print(e)
                vm_info_task.message = "{}==>{}".format(step, e)
                vm_info_task.fail_reason = "{}==>{}".format(step, e)
                vm_info_task.save()
            next_step = 'finish'
        proxbox_vm.virtual_machine_id = netbox_vm.id
        proxbox_vm.virtual_machine = netbox_vm
        proxbox_vm.save()
        vm_info_task.proxmox_vm_id = proxbox_vm.id
        vm_info_task.proxmox_vm = proxbox_vm
        vm_info_task.save()

        if step == 'finish':
            print("[OK] FINISH ALL PROCESS for: {}-{}".format(netbox_vm.name, netbox_vm.id))
            process_vm_info_args = [vm_info_task.id]
            # print(f'42. Run the next function (update_vm_status_queue for {vm_info_task_id}) ')
            queue_next_sync(vm_info_task, finish_vm_process, process_vm_info_args, 'finish_vm_process')
        else:
            process_vm_info_args = [vm_info_task.id, cluster, proxbox_vm, next_step]
            # print(f'42. Run the next function (update_vm_status_queue for {vm_info_task_id}) ')
            m = 'update_vm_process_' + next_step
            queue_next_sync(vm_info_task, update_vm_process, process_vm_info_args, m)

        # print("[ok] FINISH update_vm_status_queue")
    except Exception as e:
        print("\n\n***>Processing update_vm_process -> {}<***".format(step))
        print("Error: update_vm_process-all - {}".format(e))
        print(e)
        return "Error"


@job(QUEUE_NAME)
def process_vm_info2(vm_info_task_id, cluster=None):
    try:
        # print("\n\n***>Processing process_vm_info2<***")
        vm_info_task = get_process_vm(vm_info_task_id)
        if cluster is None:
            cluster = get_cluster_from_domain(vm_info_task.domain)
        proxbox_vm = set_get_proxbox_item(vm_info_task, cluster)
        if proxbox_vm is None:
            return

        vm_info_task.proxmox_vm_id = proxbox_vm.id
        vm_info_task.proxmox_vm = proxbox_vm
        vm_info_task.save()

        # print("Starting vm update")

        process_vm_info_args = [vm_info_task.id, cluster, proxbox_vm, 'status']
        # print(f'42. Run the next function (update_vm_process for {vm_info_task_id}) ')
        queue_next_sync(vm_info_task, update_vm_process, process_vm_info_args, 'update_vm_process')

    except Exception as e:
        print("\n\n***>Processing process_vm_info2<***")
        print("Error: update_vm_process-process_vm_info2 - {}".format(e))
        print(e)
        return "Error"


@job(QUEUE_NAME)
def process_vm_info(vm_task_id, proxmox_json, cluster=None, task_id=None):
    # print('\n\n***>Executing process_vm_info<***')
    msg = f'[Start VMs data:{vm_task_id}:{"None" if task_id is None else task_id}]'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    # print(message)

    # try:
    vm_task = SyncTask.objects.filter(id=vm_task_id).first()
    # except Exception as e:
    if vm_task is None:
        print("Error: update_vm_process-process_vm_info-vm_task - {}".format(e))
        return 'Error'
    user = vm_task.user
    remove_unused = vm_task.remove_unused
    domain = vm_task.domain
    # print('40. Getting or creating the node data sync job')
    vm_info_task = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.START_VM_SYNC)
    if task_id is None or task_id == '':
        task_id = vm_task.id

    # print('41. Updating info for the cluster data')
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

    process_vm_info_args = [vm_info_task.id, cluster]

    # print(f'42. Run the next function (process_vm_info2 for {vm_info_task.id}) ')
    # print(process_vm_info_args)
    queue_next_sync(vm_info_task, process_vm_info2, process_vm_info_args, 'process_vm_info2')

    # print("43. FINISH process_vm_info")


@job(QUEUE_NAME)
def get_vms_for_the_node(node_task_id, task_id, iteration=0):
    print('\n\n***>Executing get_vms_for_the_node<***')
    msg = f'[Start VMs data:{node_task_id}:{"None" if task_id is None else task_id}] iteration: {iteration}'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    # print(message)
    if iteration > 3:
        return f'Canceling the job'

    # try:
    node_task = SyncTask.objects.filter(id=node_task_id).first()
    # except Exception as e:
    if node_task is None:
        print('SYNC JOB NOT FOUND DELAYING IN ORDER TO WAIT FOR THE DATA BASE COMMIT')
        iteration = iteration + 1
        current_queue_args = [
            node_task_id, task_id, iteration
        ]
        custom_delay(get_vms_for_the_node, current_queue_args, None, 500)
        return f'Delaying the job'

    user = node_task.user
    remove_unused = node_task.remove_unused
    domain = node_task.domain

    # print('35. Getting or creating the node data sync job')
    vm_task = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.GET_VMS_FROM_NODES)

    if task_id is None or task_id == '':
        task_id = vm_task.id
    # print('36. Updating info for the cluster data')
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
    # print(f'37. Should delay the job {should_delay}')
    if should_delay:
        current_queue_args = [
            node_task_id, task_id, 0
        ]
        # Run the delay process if there is already other process with the same characterics is running
        # print('38. Run the delay process if there is already other process with the same characterics is running')
        cluster_nodes = delay_sync(vm_task, start_cluster_sync, current_queue_args, 1)
        return f'Delaying :{cluster_nodes.name}:{cluster_nodes.id}'
    else:
        print('\nUPDATE ALL... {}'.format(domain))
        # Get all VM/CTs from Proxmox
        node_vms_all = proxmox.cluster.resources.get(type='vm')
        cluster = get_set_cluster(proxmox)
        if len(node_vms_all) < 1:
            vm_task.done = True
            vm_task.data_instance = node_vms_all
            vm_task.fail_reason = 'No virtual machines found for the cluster'
            vm_task.save()
            current_queue_args = [
                vm_task.id
            ]
            delay_sync(vm_task, clean_left, current_queue_args, 1)
            return
        vm_task.data_instance = node_vms_all
        vm_task.save()
        counter = 0
        print(f'[OK] Setting all the vm for the cluster')
        for px_vm_each in node_vms_all:
            try:
                # if counter > 0:
                #     break

                # print(px_vm_each)
                is_template = px_vm_each.get("template")
                if is_template == 1:
                    continue
                process_vm_info_args = [
                    vm_task.id, px_vm_each, cluster, None
                ]

                # print(f'34. Run the next function (process_vm_info for {domain}) ')
                # print(process_vm_info_args)
                # print('\nvm for the domain {}'.format(domain))
                # print(px_vm_each)
                counter = counter + 1
                queue_next_sync(vm_task, process_vm_info, process_vm_info_args, 'process_vm_info')

                # vm_updated = virtual_machine(proxmox_json=px_vm_each, proxmox_session=proxmox_session, cluster=cluster)
                # virtualmachines_list.append(vm_updated)
            except Exception as e:
                print("Error: update_vm_process-px_vm_each-proxmox - {}".format(e))
                print(e)


@job(QUEUE_NAME)
def get_nodes_for_the_cluster(cluster_data_id, task_id, iteration=0):
    cluster_data = None
    try:
        # print('\n\n***>Executing get_nodes_for_the_cluster<***')
        msg = f'[Start nodes data:{cluster_data_id}:{"None" if task_id is None else task_id}] iteration: {iteration}'
        message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
        log.info(message)
        # print(message)
        if iteration > 3:
            return f'Canceling the job'
        # try:
        cluster_data = SyncTask.objects.filter(id=cluster_data_id).first()
        # except Exception as e:
        if cluster_data is None:
            print("Error: update_vm_process-get_nodes_for_the_cluster ")
            print('SYNC JOB NOT FOUND DELAYING IN ORDER TO WAIT FOR THE DATA BASE COMMIT')
            iteration = iteration + 1
            current_queue_args = [
                cluster_data_id, task_id, iteration
            ]
            custom_delay(get_nodes_for_the_cluster, current_queue_args, None, 500)
            return f'Delaying the job'
        user = cluster_data.user
        remove_unused = cluster_data.remove_unused
        domain = cluster_data.domain

        # print('29. Getting or creating the node data sync job')
        cluster_nodes = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.START_NODE_SYNC)

        if task_id is None or task_id == '':
            task_id = cluster_data.id
        # print('30. Updating info for the cluster data')
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
        print('\n\n\nNODES... {}'.format(domain))
        nodes_list = []
        node_response_list = []
        proxmox_nodes = cluster_all[1:]

        # print('Finish get_cluster_data')
        should_delay = should_delay_job_run(cluster_nodes, TaskTypeChoices.START_NODE_SYNC, domain)
        # print(f'31. Should delay the job {should_delay}')
        if should_delay:
            current_queue_args = [
                cluster_data_id, task_id, 0
            ]
            # Run the delay process if there is already other process with the same characterics is running
            # print('32. Run the delay process if there is already other process with the same characterics is running')
            cluster_nodes = delay_sync(cluster_nodes, start_cluster_sync, current_queue_args, 1)
            return f'Delaying :{cluster_nodes.name}:{cluster_nodes.id}'
        else:
            # Run the next function (start_cluster_sync)
            cluster_nodes_id = cluster_nodes.id
            # Get all NODES from Proxmox
            try:
                proxmox_session = get_session(domain)
                proxmox = proxmox_session.get('PROXMOX_SESSION')
            except Exception as e:
                print("[ERROR] update_vm_process-get_nodes_for_the_cluster-proxmox_session - {}".format(e))
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
            # print(f'33. Finish get_nodes_for_the_cluster')

            get_nodes_for_the_cluster_args = [
                cluster_nodes_id, None, 0
            ]
            # print(f'34. Run the next function (get_nodes_for_the_cluster for {domain}) ')
            queue_next_sync(cluster_nodes, get_vms_for_the_node, get_nodes_for_the_cluster_args,
                            'get_vms_for_the_node')
    except Exception as e:
        print('\n\n***>Executing get_nodes_for_the_cluster<***')
        print("Error: get_nodes_for_the_cluster- {}".format(e))
        print(e)
        if cluster_data:
            cluster_data.done = True
            cluster_data.status = TaskStatusChoices.STATUS_FAILED
            cluster_data.fail_reason = e
            cluster_data.save()
            current_queue_args = [
                cluster_data.id
            ]
            delay_sync(cluster_data, clean_left, current_queue_args, 1)
            # queue_next_sync(None, clean_left, current_queue_args, 'clean_left',
            #                 TaskStatusChoices.STATUS_SUCCEEDED)


@job(QUEUE_NAME)
def get_cluster_data(cluster_task_id, domain, task_id, iteration=0):
    print('\n\n***>Executing get_cluster_data<***')
    cluster_sync = None
    cluster_data = None
    try:
        msg = f'[Start getting cluster data:{cluster_task_id}:{domain}:{"none" if task_id is None else task_id}] iteration: {iteration}'
        message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
        log.info(message)
        print(message)
        if iteration > 3:
            return f'Canceling the job'

        try:
            cluster_sync = SyncTask.objects.get(id=cluster_task_id)
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

        # print('22. Getting or creating the cluster data sync job')
        cluster_data = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.GET_CLUSTER_DATA)

        if task_id is None or task_id == '':
            task_id = cluster_data.id

        # print('24. Updating info for the cluster data')
        cluster_data.parent = cluster_sync
        cluster_data.parent_id = cluster_sync.id
        cluster_data.name = 'Start cluster data'
        cluster_data.domain = domain
        cluster_data.status = TaskStatusChoices.STATUS_RUNNING
        cluster_data.job_id = cluster_sync.job_id
        cluster_data.save()
        # print('25. Getting proxmox session')
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
        print('[OK] Finish get_cluster_data')
        should_delay = should_delay_job_run(cluster_data, TaskTypeChoices.GET_CLUSTER_DATA, domain)
        # print(f'26. Should delay the job {should_delay}')
        if should_delay:
            current_queue_args = [
                cluster_task_id, domain, task_id, 0
            ]
            # Run the delay process if there is already other process with the same characterics is running
            # print('27. Run the delay process if there is already other process with the same characterics is running')
            cluster_data = delay_sync(cluster_data, start_cluster_sync, current_queue_args, 1)
            return f'Delaying :{cluster_data.name}:{cluster_data.id}'
        else:
            # Run the next function (start_cluster_sync)

            cluster_data_id = cluster_data.id
            get_nodes_for_the_cluster_args = [
                cluster_data_id, None, 0
            ]
            # print(f'28. Run the next function (get_nodes_for_the_cluster for {domain}) ')
            queue_next_sync(cluster_data, get_nodes_for_the_cluster, get_nodes_for_the_cluster_args,
                            'get_nodes_for_the_cluster')

        return f'Finish...'

    except Exception as e:
        print('\n\n***>Executing get_cluster_data<***')
        print("Error: get_cluster_data-cluster-all {}".format(e))
        print(e)
        if cluster_data:
            cluster_data.status = TaskStatusChoices.STATUS_FAILED
            cluster_data.fail_reason = e
            cluster_data.save()
            current_queue_args = [
                cluster_data.id
            ]
            delay_sync(cluster_data, clean_left, current_queue_args, 1)

        if cluster_sync:
            cluster_sync.status = TaskStatusChoices.STATUS_FAILED
            cluster_sync.fail_reason = e
            cluster_sync.save()
            current_queue_args = [
                cluster_sync.id
            ]
            delay_sync(cluster_sync, clean_left, current_queue_args, 1)

            # cluster_sync.done = True

            # father = SyncTask.objects.filter(id=cluster_sync.parent_id).first()
            # father.done = True
            # father.status = TaskStatusChoices.STATUS_FAILED
            # father.save()

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
            sync_job = SyncTask.objects.get(id=sync_job_id)
        except Exception as e:
            print("[ERROR] start_cluster_sync-sync_job {}".format(e))
            print('SYNC JOB NOT FOUND DELAYING IN ORDER TO WAIT FOR THE DATA BASE COMMIT')
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
            task_id = cluster_sync.id
        # print('18. Set parent for the cluster job')
        cluster_sync.parent = sync_job
        cluster_sync.parent_id = sync_job.id
        cluster_sync.name = 'Start cluster sync'
        cluster_sync.job_id = sync_job.job_id
        cluster_sync.save()

        should_delay = should_delay_job_run(cluster_sync, TaskTypeChoices.START_CLUSTER_SYNC, None)
        # print(f'19. Should delay the job {should_delay}')
        if should_delay:
            current_queue_args = [
                sync_job_id,
                cluster_sync.id,
                0
            ]
            # Run the delay process if there is already other process with the same characterics is running
            # print('20. Run the delay process if there is already other process with the same characterics is running')
            cluster_sync = delay_sync(cluster_sync, start_cluster_sync, current_queue_args, 1)
            return f'Delaying :{cluster_sync.name}:{cluster_sync.id}'
        else:
            # Run the next function (start_cluster_sync)
            for key in proxmox_sessions:
                try:
                    session = proxmox_sessions[key]
                    domain = session['PROXMOX']
                    cluster_task_id = cluster_sync.id
                    get_cluster_data_args = [
                        cluster_task_id,
                        domain,
                        None,
                        0
                    ]
                    # print(f'21. Run the next function (get_cluster_data for {domain}) ')
                    queue_next_sync(cluster_sync, get_cluster_data, get_cluster_data_args, 'get_cluster_data')
                except Exception as e:
                    print("Error: start_cluster_sync-proxmox_sessions {}".format(e))
                    message = "OS error: {0}".format(e)
                    print(message)
                    log.error(e)
            return f'Finish:{cluster_sync.name}:{cluster_sync.id}'
    except Exception as e:
        print("Error: start_cluster_sync-all-1 {}".format(e))
        print(e)
        return f'Error'


def job_start_sync(task_id, user, remove_unused):
    print('\n\n***>Executing job_start_sync<***')
    # print('1. Start job_start_sync function')
    sync_task = get_or_create_sync_job(task_id, user, remove_unused)
    if sync_task.job_id is None:
        sync_task.job_id = uuid.uuid4()
        sync_task.save()
    if task_id is None or task_id == '':
        task_id = sync_task.id

    should_delay = should_delay_job_run(sync_task, TaskTypeChoices.START_SYNC, None)
    # print(f'8. Should delay the job {should_delay}')
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
            start_sync.id,
            user,
            remove_unused
        ]
        # Run the delay process if there is already other process with the same characterics is running
        # print('9. Run the delay process if there is already other process with the same characterics is running')
        sync_task = delay_sync(sync_task, start_sync, current_queue_args, 1)
    else:
        next_queue_args = [
            task_id,
            None,
            0
        ]
        # Run the next function (start_cluster_sync)
        # print('14. Run the next function (start_cluster_sync) ')
        sync_task.start_time = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
        sync_task.save()
        sync_task = queue_next_sync(sync_task, start_cluster_sync, next_queue_args, 'start_cluster_sync')
    return sync_task


@job(QUEUE_NAME)
def start_sync(id, user, remove_unused=True):
    print('\n\n***>Executing start_sync<***')
    msg = '[Proxbox - Netbox plugin | Update All | queue]'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    print(message)
    sync_task = job_start_sync(id, user, True)
    print('Finish start_sync')
    if sync_task is None:
        return f'No sync task created'
    else:
        return f'Finish:{sync_task.name}:{sync_task.id}'
