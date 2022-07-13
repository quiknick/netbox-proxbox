import pytz
import os

from .others.logger import log
from datetime import datetime, timedelta
from django_rq import job, get_queue, get_scheduler
from netbox_proxbox.choices import TaskTypeChoices, TaskStatusChoices
from netbox_proxbox.models import SyncTask
from .proxbox_api.plugins_config import (
    # PROXMOX_SESSIONS as proxmox_sessions,
    QUEUE_NAME
)

# from .proxbox_api import (
#     updates,
#     create,
#     remove,
# )

TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")


#
#
# #
# #
# # TODO (alejandro):  These function can be part of sync?
# def get_or_create_sync_job(
#         task_id,
#         user,
#         remove_unused=True,
#         task_type=TaskTypeChoices.START_SYNC,
#         message='New synchronization job'
#
# ):
#     try:
#         if task_id is None or task_id == '':
#             sync_job = None
#         else:
#             sync_job = SyncTask.objects.get(task_id=task_id)
#     except Exception as e:
#         print(e)
#         sync_job = None
#     if sync_job is None:
#         if task_type is None or task_type == '':
#             task_type = TaskTypeChoices.START_SYNC
#         sync_job = SyncTask(
#             task_type=task_type,
#             done=False,
#             name='Sync',
#             status=TaskStatusChoices.STATUS_UNKNOWN,
#             message=message,
#             fail_reason='',
#             scheduled_time=(datetime.now()).replace(microsecond=0, tzinfo=pytz.utc),
#             user=user,
#             remove_unused=remove_unused
#         )
#         sync_job.save()
#     return sync_job
#
#
# #
# #
# def delay_sync(
#         sync_task,
#         schedule_function,
#         schedule_args,
#         plus_time=5
# ):
#     if sync_task is None:
#         raise Exception("Object sync_task can't be None")
#
#     status = TaskStatusChoices.STATUS_SCHEDULED
#     msg = f'Delaying the run by {plus_time} minutes'
#     message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
#     log.info(message)
#     print(message)
#
#     now = datetime.now()
#     # next execution
#     now_plus_time = (now + timedelta(minutes=plus_time)).replace(microsecond=0, tzinfo=pytz.utc)
#     sync_task.status = status
#     sync_task.message = message
#     sync_task.scheduled_time = now_plus_time
#     # Save the task
#     sync_task.save()
#
#     # Schedule the execution
#     scheduler = get_scheduler(QUEUE_NAME)
#     schedule_job = scheduler.schedule(
#         scheduled_time=now_plus_time,
#         func=schedule_function,
#         args=schedule_args,
#     )
#     sync_task.job_id = schedule_job.id
#     sync_task.save()
#     return sync_task
#
#
# #
# #
# def queue_next_sync(
#         sync_task,
#         next_queue,
#         next_queue_args=None,
#         next_queue_function_string=None
# ):
#     if sync_task is None:
#         print('The task is none')
#         raise Exception("Object sync_task can't be None")
#
#     status = TaskStatusChoices.STATUS_RUNNING
#     msg = 'Queue next sync'
#     if next_queue_function_string is not None and next_queue_function_string != '':
#         msg = msg + next_queue_function_string
#     message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
#     log.info(message)
#     print(message)
#     sync_task.status = status
#     sync_task.message = message
#     sync_task.scheduled_time = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
#
#     # Save the task
#     sync_task.save()
#     queue = get_queue(QUEUE_NAME)
#     queue_job = queue.enqueue_job(
#         queue.create_job(
#             func=next_queue,
#             args=next_queue_args,
#         )
#     )
#     sync_task.job_id = queue_job.id
#     sync_task.save()
#     return sync_task
#
#
# #
# #
# def should_delay_job_run_1(
#         sync_task,
#         task_type,
#         domain=None
# ):
#     print('If possible only run one synchronization at the time')
#     # If possible only run one synchronization at the time
#     # get all running task that have type START_SYNC
#     if domain is None:
#         print('get all running task that have type START_SYNC no Domain')
#         running_job = SyncTask.objects.filter(
#             task_type=task_type,
#             done=False,
#             status=TaskStatusChoices.STATUS_RUNNING
#         )
#     else:
#         print('get all running task that have type START_SYNC')
#         running_job = SyncTask.objects.filter(
#             task_type=task_type,
#             done=False,
#             domain=domain,
#             status=TaskStatusChoices.STATUS_RUNNING
#         )
#     # Count how many task are running
#     print('Count how many task are running')
#     total_running_jobs = running_job.count()
#     # Get the task by its task_id if no task_id is set then it will be created later
#     print('Get the task by its task_id if no task_id is set then it will be created later')
#     for job in running_job:
#         if sync_task is not None:
#             if sync_task.task_id == job.task_id:
#                 total_running_jobs = 0
#                 break
#     # if another sync process is running delay the current execution
#     print('if another sync process is running delay the current execution')
#     try:
#         if total_running_jobs > 0:
#             return True
#         else:
#             return False
#     except Exception as e:
#         return True
#
#
# #
# #
# def job_start_sync(
#         task_id,
#         user,
#         remove_unused=True
# ):
#     print('fuynction correctly called')
#     return 'A'
#     # sync_task = get_or_create_sync_job(task_id, user, remove_unused)
#     #
#     # if task_id is None or task_id == '':
#     #     task_id = sync_task.task_id
#     # # Check if the process should be delay or not
#     # print('Check if the process should be delay or not')
#     # should_delay = should_delay_job_run_1(sync_task, TaskTypeChoices.START_SYNC, None)
#     # # # if another sync process is running delay the current execution
#     # # try:
#     # #     if should_delay:
#     # #         current_queue_args = [
#     # #             task_id,
#     # #             user,
#     # #             remove_unused
#     # #         ]
#     # #         # Run the delay process if there is already other process with the same characterics is running
#     # #         print('Run the delay process if there is already other process with the same characterics is running')
#     # #         sync_task = delay_sync(sync_task, start_sync, current_queue_args, 1)
#     # #     else:
#     # #         next_queue_args = [
#     # #             task_id,
#     # #             None
#     # #         ]
#     # #         # Run the next function (start_cluster_sync)
#     # #         print('Run the next function (start_cluster_sync) ')
#     # #         try:
#     # #             sync_task = queue_next_sync(sync_task, start_cluster_sync, next_queue_args, 'start_cluster_sync')
#     # #         except Exception as e:
#     # #             print(e)
#     # #             raise e
#     # # except Exception as e:
#     # #     log.error(e)
#     # #     if sync_task is None:
#     # #         try:
#     # #             sync_task.fail_reason = str(e)
#     # #             sync_task.save()
#     # #         except Exception as e:
#     # #             log.error(e)
#     # #             print(e)
#     #
#     # return sync_task
#
#
# #
# #
# # def get_session(domain):
# #     session = None
# #     for key in proxmox_sessions:
# #         try:
# #             if domain == key:
# #                 session = proxmox_sessions[key]
# #         except Exception as e:
# #             message = "OS error: {0}".format(e)
# #             print(message)
# #     return session
#
def a_function(task_id, user, remove_unused):
    print('fuynction correctly called')


@job(QUEUE_NAME)
def start_sync(task_id, user, remove_unused=True):
    # try:
    msg = '[Proxbox - Netbox plugin | Update All | queue]'
    message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    log.info(message)
    print(message)
    a_function(task_id, user, remove_unused)
    # job_start_sync(task_id, user, remove_unused)
    print('test ouput')
    return f'Outpur'
    # except Exception as e:
    #     print(e)
    #     raise Exception(e)
    # pass
    # try:
    #     msg = '[Proxbox - Netbox plugin | Update All | queue]'
    #     message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
    #     log.info(message)
    #     print(message)
    #     sync_task = job_start_sync(task_id, user, remove_unused)
    #
    #     if sync_task is None:
    #         return f'No sync task created'
    #     else:
    #         return f'Finish:{sync_task.name}:{sync_task.task_id}'
    # except Exception as e:
    #     print(e)
#
#
# @job(QUEUE_NAME)
# def start_cluster_sync(sync_job_id, task_id):
#     msg = f'[Start cluster sync:{sync_job_id}]'
#     message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
#     log.info(message)
#     print(message)
#     # try:
#     #     msg = f'[Start cluster sync:{sync_job_id}]'
#     #     message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
#     #     log.info(message)
#     #     print(message)
#     #     sync_job = SyncTask.objects.get(task_id=sync_job_id)
#     #     user = sync_job.user
#     #     remove_unused = sync_job.remove_unused
#     #     cluster_sync = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.START_CLUSTER_SYNC)
#     #     if task_id is None or task_id == '':
#     #         task_id = cluster_sync.task_id
#     #     cluster_sync.parent = sync_job
#     #     cluster_sync.parent_id = sync_job.id
#     #     cluster_sync.name = 'Start cluster sync'
#     #     cluster_sync.save()
#     #
#     #     should_delay = should_delay_job_run(cluster_sync, TaskTypeChoices.START_CLUSTER_SYNC, None)
#     #
#     #     if should_delay:
#     #         schedule_args = [
#     #             sync_job_id,
#     #             task_id
#     #         ]
#     #         cluster_sync = delay_sync(cluster_sync, start_cluster_sync, schedule_args)
#     #         return f'Job delay: {cluster_sync.name}:{cluster_sync.task_id}'
#     #
#     #     for key in proxmox_sessions:
#     #         try:
#     #             session = proxmox_sessions[key]
#     #             get_cluster_data_args = [
#     #                 cluster_sync.id,
#     #                 session['PROXMOX'],
#     #                 None
#     #             ]
#     #             queue_next_sync(cluster_sync, get_cluster_data, get_cluster_data_args, 'get_cluster_data')
#     #         except Exception as e:
#     #             message = "OS error: {0}".format(e)
#     #             print(message)
#     #             log.error(e)
#     #     return f'Finish:{cluster_sync.name}:{cluster_sync.task_id}'
#     # except Exception as e:
#     #     print(e)
#     #     return f'Error'
#
#
# @job(QUEUE_NAME)
# def get_cluster_data(cluster_task_id, domain, task_id):
#     # try:
#     #     msg = f'[Start getting cluster data:{cluster_task_id}:{domain}]'
#     #     message = f'-> {datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")} - {msg}'
#     #     log.info(message)
#     #     print(message)
#     #     cluster_sync = SyncTask.objects.get(task_id=cluster_task_id)
#     #     user = cluster_sync.user
#     #     remove_unused = cluster_sync.remove_unused
#     #
#     #     cluster_data = get_or_create_sync_job(task_id, user, remove_unused, TaskTypeChoices.START_CLUSTER_SYNC)
#     #     if task_id is None or task_id == '':
#     #         task_id = cluster_data.task_id
#     #     cluster_data.parent = cluster_sync
#     #     cluster_data.parent_id = cluster_sync.id
#     #     cluster_data.name = 'Start cluster data'
#     #     cluster_data.save()
#     #
#     #     proxmox_session = get_session(domain)
#     #     proxmox = proxmox_session.get('PROXMOX_SESSION')
#     #     cluster_all = proxmox.cluster.status.get()
#     #     # cluster = create.virtualization.cluster(proxmox)
#     #     # print('\n\n\nCLUSTER...')
#     #     # print('[OK] CLUSTER created. -> {}'.format(cluster.name))
#     #
#     #     # proxmox_cluster = cluster_all[0]
#     #
#     #     return f'Finish...'
#     # except Exception as e:
#     #     print(e)
#     #     return f'Error'
#
#     # # Get all NODES from Proxmox
#     # for px_node_each in proxmox_nodes:
#     #     node_updated = nodes(proxmox_json=px_node_each, proxmox_cluster=proxmox_cluster, proxmox=proxmox)
#     #     nodes_list.append(node_updated)
#
#     # sync_task = sync_start_analysis(task_id, user, start_sync, start_cluster_sync, 'Cluster sync',
#     #                                 TaskTypeChoices.START_CLUSTER_SYNC, remove_unused)
#     # sync_task.parent = sync_job.id
#     # sync_task.save()
#     # proxmox_session = get_session(domain)
#     pass
