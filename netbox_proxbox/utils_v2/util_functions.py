from .virtualmachine import get_nb_by_, virtual_machine

try:
    import os
    import pytz
    from django_rq import job, get_queue, get_scheduler
    from datetime import datetime, timedelta

    from .cluster import get_set_cluster
    from ..others.logger import log
    from ..choices import TaskTypeChoices, TaskStatusChoices, RemoveStatusChoices
    from ..proxbox_api.plugins_config import (
        QUEUE_NAME,
        PROXMOX_SESSIONS as proxmox_sessions,
    )

    from ..models import SyncTask
except Exception as e:
    print(e)
    raise e

TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")


def get_session(domain):
    session = None
    for key in proxmox_sessions:
        try:
            if domain == key:
                session = proxmox_sessions[key]
        except Exception as e:
            print("Error: get_session-1 - {}".format(e))
            message = "OS error: {0}".format(e)
            print(message)
    return session


def custom_delay(schedule_function, schedule_args, delay_until=None, plus_mili=500):
    if delay_until is None:
        now = datetime.now()
        if plus_mili is None:
            plus_mili = 500
        delay_until = (now + timedelta(milliseconds=plus_mili)).replace(microsecond=0, tzinfo=pytz.utc)
    # Schedule the execution
    scheduler = get_scheduler(QUEUE_NAME)
    schedule_job = scheduler.schedule(
        scheduled_time=delay_until,
        func=schedule_function,
        args=schedule_args,
    )
    return schedule_job


def delay_sync(
        sync_task,
        schedule_function,
        schedule_args,
        plus_time=5
):
    # print('10. Delaying the current execution')
    if sync_task is None:
        raise Exception("Object sync_task can't be None")

    status = TaskStatusChoices.STATUS_SCHEDULED
    msg = f'[OK] Delaying the run by {plus_time} minutes'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    # print(message)
    now = datetime.now()

    # next execution
    now_plus_time = (now + timedelta(minutes=plus_time)).replace(microsecond=0, tzinfo=pytz.utc)
    sync_task.status = status
    sync_task.message = message
    sync_task.scheduled_time = now_plus_time
    # print('11. Save the task')
    sync_task.save()

    # Schedule the execution
    schedule_job = custom_delay(schedule_function, schedule_args, now_plus_time)
    # scheduler = get_scheduler(QUEUE_NAME)
    # schedule_job = scheduler.schedule(
    #     scheduled_time=now_plus_time,
    #     func=schedule_function,
    #     args=schedule_args,
    # )
    # sync_task.job_id = schedule_job.id
    # sync_task.save()
    # print(f'13. Next task successfully queue with id: {schedule_job.id}')

    return sync_task


def queue_next_sync(
        sync_task,
        next_queue,
        next_queue_args=None,
        next_queue_function_string=None,
        task_Status=None
):
    # print('15. Queueing the next execution')
    # if sync_task is None:
    #     print('The task is none')
    #     raise Exception("Object sync_task can't be None")
    if task_Status is not None:
        status = task_Status
    else:
        status = TaskStatusChoices.STATUS_RUNNING

    msg = 'Queue next sync'
    if next_queue_function_string is not None and next_queue_function_string != '':
        msg = msg + next_queue_function_string
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    # print(message)
    try:
        if sync_task is not None:
            sync_task.status = status
            sync_task.message = message
            sync_task.scheduled_time = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
            # print('16. Save the task')
            sync_task.save()
    except Exception as e:
        print("Error: queue_next_sync-1 - {}".format(e))
        print(e)
        raise e
    # Save the task

    try:
        queue = get_queue(QUEUE_NAME)
        queue_job = queue.enqueue_job(
            queue.create_job(
                func=next_queue,
                args=next_queue_args,
            )
        )
        # if sync_task is not None:
        #     sync_task.job_id = queue_job.id
        #     sync_task.save()
    except Exception as e:
        print("Error: queue_next_sync-2 - {}".format(e))
        print(e)
        raise e
    # print(f'17. Next task successfully queue with id: {queue_job.id}')
    return sync_task


def get_or_create_sync_job(
        task_id,
        user,
        remove_unused=True,
        task_type=TaskTypeChoices.START_SYNC,
        message='New synchronization job'

):
    # print('2. Start get_or_create_sync_job function')
    try:
        # try to get the sync job, if the task_id is none or the sync job doesn't exists prepare everything to create
        # a new one
        if task_id is None or task_id == '':
            sync_job = None
        else:
            # print(f'24. Trying to the get the sync job with id: {task_id}')
            sync_job = SyncTask.objects.get(id=task_id)
    except Exception as e:
        print("Error: get_or_create_sync_job-1 - {}".format(e))
        print(e)
        sync_job = None

    if sync_job is None:
        if task_type is None or task_type == '':
            task_type = TaskTypeChoices.START_SYNC
        # print(f'23. Creating new sync job for {task_type}')
        sync_job = SyncTask(
            task_type=task_type,
            done=False,
            name='Sync',
            status=TaskStatusChoices.STATUS_UNKNOWN,
            message=message,
            fail_reason='',
            scheduled_time=(datetime.now()).replace(microsecond=0, tzinfo=pytz.utc),
            user=user,
            remove_unused=remove_unused
        )
        sync_job.save()

    return sync_job


def should_delay_job_run(
        sync_task,
        task_type,
        domain=None
):
    # print('3. If possible only run one synchronization at the time')
    # If possible only run one synchronization at the time
    # get all running task that have type START_SYNC
    if domain is None:
        # print('4. get all running task that have type START_SYNC no Domain')
        running_job = SyncTask.objects.filter(
            task_type=task_type,
            done=False,
            status=TaskStatusChoices.STATUS_RUNNING
        )
    else:
        # print('4. get all running task that have type START_SYNC')
        running_job = SyncTask.objects.filter(
            task_type=task_type,
            done=False,
            domain=domain,
            status=TaskStatusChoices.STATUS_RUNNING
        )
    # Count how many task are running
    # print('5. Count how many task are running')
    total_running_jobs = running_job.count()
    # print(f'6. Running task {total_running_jobs}')

    # Get the task by its task_id if no task_id is set then it will be created later
    # print('7. Get the task by its task_id if no task_id is set then it will be created later')
    for job in running_job:
        if sync_task is not None:
            if sync_task.id == job.id:
                total_running_jobs = 0
                break
    try:
        if total_running_jobs > 0:
            return True
        else:
            return False
    except Exception as e:
        print("Error: should_delay_job_run-1 - {}".format(e))
        return True
    return True


def get_process_vm(vm_info_task_id):
    # print('Executing process_vm_info2')
    msg = f'[Start process_vm_info2:{vm_info_task_id}]'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    # print(message)

    try:
        vm_info_task = SyncTask.objects.get(id=vm_info_task_id)
        return vm_info_task
    except Exception as e:
        print("Error: get_process_vm-1 - {}".format(e))
        raise e


def get_cluster_from_domain(domain):
    # print('[OK] Getting cluster')
    proxmox_session = get_session(domain)
    proxmox = proxmox_session.get('PROXMOX_SESSION')
    cluster = get_set_cluster(proxmox)
    return cluster


def nb_search_data_(proxmox_json, domain, cluster=None):
    proxmox_session = get_session(domain)
    proxmox = proxmox_session.get('PROXMOX_SESSION')
    proxmox_vm_name = None

    # Decide whether 'proxmox_json' or other args (id, proxmox_id and proxmox_name) will be used
    if proxmox_json != None:
        proxmox_vm_name = proxmox_json['name']

    if proxmox_vm_name == None:
        return None

    # Search Netbox object by name gotten from Proxmox
    # print('[OK] Getting node')
    node = proxmox_json['node']
    if cluster is None:
        # print('[OK] Getting cluster')
        cluster = get_set_cluster(proxmox)

    # print('[OK] Getting vmid')
    vmid = proxmox_json['vmid']
    return cluster, vmid, node, proxmox_vm_name, proxmox_session, proxmox


def set_vm(vm_info_task, cluster=None):
    # print('[OK] STARTING PROCESS FOR VIRTUAL MACHINE')
    proxmox_json = vm_info_task.data_instance

    cluster, vmid, node, proxmox_vm_name, proxmox_session, proxmox = nb_search_data_(proxmox_json, vm_info_task.domain,
                                                                                     cluster)
    netbox_vm = get_nb_by_(cluster.name, vmid, node, proxmox_vm_name)

    # print("GOT VM")
    # print(netbox_vm)
    # vm_on_netbox = is_vm_on_netbox(netbox_vm)
    if netbox_vm == None:
        print('[OK] VM does not exist on Netbox -> {}'.format(proxmox_vm_name))
        # Analyze if VM was sucessfully created.
        netbox_vm = virtual_machine(proxmox, proxmox_json)
    # vm_info_task.virtual_machine = netbox_vm
    vm_info_task.virtual_machine_id = netbox_vm.id
    vm_info_task.save()
    # print("VM CREATED")
    # print(netbox_vm)
    return netbox_vm
