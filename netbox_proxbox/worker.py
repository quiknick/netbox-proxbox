import pytz
import os

from .others.logger import log
from datetime import datetime, timedelta
from django_rq import job, get_queue, get_scheduler
from netbox_proxbox.choices import TaskTypeChoices, TaskStatusChoices
from netbox_proxbox.models import SyncTask
from .proxbox_api.plugins_config import (
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
    QUEUE_NAME
)

TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")


def delay_sync(
        sync_task,
        user,
        schedule_queue,
        schedule_queue_args_fields=None,
        name='Sync',
        remove_unused=True,
        plus_time=5,
        task_type=TaskTypeChoices.UNDEFINED
):
    status = TaskStatusChoices.STATUS_SCHEDULED
    msg = f'A synchronization is already running, delaying the run by {plus_time} minutes'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    print(message)

    now = datetime.now()
    # next execution
    now_plus_time = (now + timedelta(minutes=plus_time)).replace(microsecond=0, tzinfo=pytz.utc)
    # if there is no sync task create it
    if sync_task is None:
        sync_task = SyncTask(
            task_type=task_type,
            done=False,
            name=name,
            status=status,
            message=message,
            fail_reason='',
            scheduled_time=now_plus_time,
            user=user,
            remove_unused=remove_unused
        )
    else:
        # else update the task
        sync_task.user = user
        sync_task.status = status
        sync_task.message = message
        sync_task.scheduled_time = now_plus_time
        sync_task.remove_unused = remove_unused

    if sync_task is None:
        return None

    # Save the task
    sync_task.save()
    schedule_args = None
    if schedule_queue_args_fields is None:
        schedule_queue_args_fields = ['task_id', 'user', 'remove_unused']

    for p in schedule_queue_args_fields:
        if not (p == ''):
            v = eval(f'sync_task.{p}')
            schedule_args.append(v)

    # Schedule the execution
    scheduler = get_scheduler(QUEUE_NAME)
    schedule_job = scheduler.schedule(
        scheduled_time=now_plus_time,
        func=schedule_queue,
        args=schedule_args,
    )
    sync_task.job_id = schedule_job.id
    sync_task.save()
    return sync_task


def begin_sync(
        sync_task,
        user,
        next_queue,
        next_queue_args_fields=None,
        name='Sync',
        remove_unused=True,
        task_type=TaskTypeChoices.UNDEFINED
):
    status = TaskStatusChoices.STATUS_RUNNING,
    msg = 'Synchronization Starting'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    print(message)
    # if there is no sync task create it
    if sync_task is None:
        sync_task = SyncTask(
            task_type=task_type,
            name=name,
            done=False,
            status=status,
            message=message,
            fail_reason='',
            scheduled_time=(datetime.now()).replace(microsecond=0, tzinfo=pytz.utc),
            user=user,
            remove_unused=remove_unused
        )
    else:
        # else update the task
        sync_task.user = user
        sync_task.status = status
        sync_task.message = message
        sync_task.scheduled_time = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
        sync_task.remove_unused = remove_unused

    if sync_task is None:
        return None
    # Save the task
    sync_task.save()
    schedule_args = []
    if next_queue_args_fields is None:
        next_queue_args_fields = ['task_id']

    for p in next_queue_args_fields:
        if not (p == ''):
            v = eval(f'sync_task.{p}')
            schedule_args.append(v)
    schedule_args.append(None)
    queue = get_queue(QUEUE_NAME)
    queue_job = queue.enqueue_job(
        queue.create_job(
            func=next_queue,
            args=schedule_args,
        )
    )
    sync_task.job_id = queue_job.id
    sync_task.save()
    return sync_task


def sync_start_analysis(
        task_id,
        user,
        current_queue,
        current_queue_args_fields,
        next_queue,
        next_queue_args_fields,
        name='Sync',
        domain=None,
        task_type=TaskTypeChoices.START_SYNC,
        remove_unused=True
):
    # In the possible only run one synchronization at the time
    # get all running task that have type START_SYNC
    if domain is None:
        running_syncs = SyncTask.objects.filter(task_type=task_type,
                                                done=False,
                                                status=TaskStatusChoices.STATUS_RUNNING)
    else:
        running_syncs = SyncTask.objects.filter(task_type=task_type,
                                                done=False,
                                                domain=domain,
                                                status=TaskStatusChoices.STATUS_RUNNING)
    # Count how many task are running
    total_running_syncs = running_syncs.count()
    # Get the task by its task_id if no task_id is set then it will be created later
    if task_id is not None:
        sync_task = SyncTask.objects.get(task_id=task_id)
    else:
        sync_task = None
    for t in running_syncs:
        if sync_task is not None:
            if sync_task.task_id == t.task_id:
                total_running_syncs = 0
                break
    # if another sync process is running delay the current execution
    try:
        if total_running_syncs > 0:
            sync_task = delay_sync(sync_task, user, current_queue, current_queue_args_fields, name, remove_unused, 1,
                                   task_type)
        else:
            sync_task = begin_sync(sync_task, user, next_queue, next_queue_args_fields, name, remove_unused, task_type)
    except Exception as e:
        log.error(e)
        if sync_task is None:
            try:
                sync_task.fail_reason = str(e)
                sync_task.save()
            except Exception as e:
                log.error(e)
                print(e)

    return sync_task


def get_session(domain):
    session = None
    for key in proxmox_sessions:
        try:
            if domain == key:
                session = proxmox_sessions[key]
        except Exception as e:
            message = "OS error: {0}".format(e)
            print(message)
    return session


@job(QUEUE_NAME)
def start_sync(task_id, user, remove_unused=True):
    try:
        msg = '[Proxbox - Netbox plugin | Update All | queue]'
        message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
        log.info(message)
        print(message)
        current_queue_args_fields = ['task_id', 'user', 'remove_unused']
        next_queue_args_fields = ['task_id']
        sync_task = sync_start_analysis(task_id, user, start_sync, current_queue_args_fields, start_cluster_sync,
                                        next_queue_args_fields, 'Sync', None, TaskTypeChoices.START_SYNC, remove_unused)

        if sync_task is None:
            return f'No sync task created'
        else:
            return f'Finish:{sync_task.name}:{sync_task.task_id}'
    except Exception as e:
        print(e)
    # msg = '[Proxbox - Netbox plugin | Update All | queue]'
    # message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    # log.info(message)
    # # In the possible only run one synchronization at the time
    # # get all running task that have type START_SYNC
    # running_syncs = SyncTask.objects.filter(task_type=TaskTypeChoices.START_SYNC, done=False,
    #                                         status=TaskStatusChoices.STATUS_RUNNING)
    # # Count how many task are running
    # total_running_syncs = running_syncs.count()
    # # Get the task by its task_id if no task_id is set then it will be created later
    # if task_id is not None:
    #     sync_task = SyncTask.objects.get(task_id=task_id)
    # else:
    #     sync_task = None
    # for t in running_syncs:
    #     if sync_task is not None:
    #         if sync_task.task_id == t.task_id:
    #             total_running_syncs = 0
    #             break
    # # if another sync process is running delay the current execution
    # try:
    #     if total_running_syncs > 0:
    #         sync_task = delay_sync(sync_task, user, TaskStatusChoices.STATUS_SCHEDULED,
    #                                'Sync', remove_unused, 1, TaskTypeChoices.START_SYNC)
    #     else:
    #         sync_task = begin_sync(sync_task, user, TaskStatusChoices.STATUS_SCHEDULED,
    #                                'Sync', remove_unused, TaskTypeChoices.UNDEFINED)
    # except Exception as e:
    #     log.error(e)
    #     if sync_task is None:
    #         try:
    #             sync_task.fail_reason = str(e)
    #             sync_task.save()
    #         except Exception as e:
    #             log.error(e)
    #
    # return f'Finish:{sync_task.name}:{sync_task.task_id}'


@job(QUEUE_NAME)
def start_cluster_sync(sync_task_id, task_id):
    msg = f'[Start cluster sync:{sync_task_id}]'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    print(message)
    sync_job = SyncTask.objects.get(task_id=sync_task_id)
    user = sync_job.user
    remove_unused = sync_job.remove_unused
    sync_task = sync_start_analysis(task_id, user, start_sync, start_cluster_sync, 'Cluster sync',
                                    TaskTypeChoices.START_CLUSTER_SYNC, remove_unused)
    sync_task.parent = sync_job.id
    sync_task.save()

    if sync_task is not None:
        if not (sync_task.status == TaskStatusChoices.STATUS_RUNNING):
            for key in proxmox_sessions:
                try:
                    session = proxmox_sessions[key]
                    queue = get_queue(QUEUE_NAME)
                    queue_job = queue.enqueue_job(
                        queue.create_job(
                            func=get_cluster_data,
                            args=[sync_task.task_id, session.PROXMOX],
                        )
                    )
                    sync_task.job_id = queue_job.id
                    sync_task.save()
                except Exception as e:
                    message = "OS error: {0}".format(e)
                    print(message)
                    log.error(e)
        return f'No sync task created'
    else:
        return f'Finish:{sync_task.name}:{sync_task.task_id}'


@job(QUEUE_NAME)
def get_cluster_data(cluster_task_id, domain, task_id):
    msg = f'[Start getting cluster data:{cluster_task_id}]'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    print(message)
    # cluster_task = SyncTask.objects.get(task_id=cluster_task_id)
    # user = cluster_task.user
    # remove_unused = cluster_task.remove_unused
    # sync_task = sync_start_analysis(task_id, user, start_sync, start_cluster_sync, 'Cluster sync',
    #                                 TaskTypeChoices.START_CLUSTER_SYNC, remove_unused)
    # sync_task.parent = sync_job.id
    # sync_task.save()
    # proxmox_session = get_session(domain)
    pass
