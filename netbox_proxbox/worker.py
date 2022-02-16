import pytz

from datetime import datetime, timedelta
from django_rq import job, get_queue, get_scheduler
from netbox_proxbox.choices import TaskTypeChoices, TaskStatusChoices
from netbox_proxbox.models import SyncTask

from .proxbox_api.plugins_config import QUEUE_NAME


def delay_start_sync(sync_task, user, plus_time=5):
    message = '-> A synchronization is already running, delaying the run by 5 minutes'
    now = datetime.now()
    # next execution
    now_plus_time = now + timedelta(minutes=plus_time)
    # if there is no sync task create it
    if sync_task is None:
        sync_task = SyncTask(
            task_type=TaskTypeChoices.START_SYNC,
            done=False,
            status=TaskStatusChoices.STATUS_SCHEDULED,
            message=message,
            fail_reason='',
            scheduled_time=now_plus_time,
            log=message + '\n',
            user=user | ''
        )
    else:
        # else update the task
        sync_task.user = user
        sync_task.status = TaskStatusChoices.STATUS_SCHEDULED
        sync_task.message = message
        sync_task.log += message + '\n'
        sync_task.scheduled_time = now_plus_time

    # Save the task
    sync_task.save()

    # Schedule the execution
    scheduler = get_scheduler(QUEUE_NAME)
    schedule_job = scheduler.schedule(
        scheduled_time=now_plus_time,
        func="netbox_proxbox.worker.start_sync",
        args=[sync_task.task_id, user],
    )
    sync_task.job_id = schedule_job.id
    sync_task.save()
    return sync_task


def begin_start_sync(sync_task, user):
    message = '-> Synchronization Starting'
    # if there is no sync task create it
    if sync_task is None:
        sync_task = SyncTask(
            task_type=TaskTypeChoices.START_SYNC,
            name='Sync',
            done=False,
            status=TaskStatusChoices.STATUS_RUNNING,
            message=message,
            fail_reason='',
            scheduled_time=datetime.now(),
            log=message + '\n',
            user=user | ''
        )
    else:
        # else update the task
        sync_task.user = user
        sync_task.status = TaskStatusChoices.STATUS_RUNNING
        sync_task.message = message
        sync_task.log += message + '\n'
        sync_task.scheduled_time = datetime.now()

    # Save the task
    sync_task.save()
    queue = get_queue(QUEUE_NAME)
    queue_job = queue.enqueue_job(
        queue.create_job(
            func="netbox_proxmox.worker.start_cluster_sync",
            args=[sync_task],
            timeout=90000,
        )
    )
    sync_task.job_id = queue_job.id
    sync_task.save()
    return sync_task


@job(QUEUE_NAME)
def start_sync(task_id, user):
    # In the possible only run one synchronization at the time
    # get all running task that have type START_SYNC
    running_syncs = SyncTask.objects.filter(task_type=TaskTypeChoices.START_SYNC, done=False,
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
    if total_running_syncs > 0:
        sync_task = delay_start_sync(sync_task, user, 5)
    else:
        sync_task = begin_start_sync(sync_task, user)

    return f'Finish:{sync_task.name}:{sync_task.task_id}'


@job(QUEUE_NAME)
def start_cluster_sync():
    pass
