# from django.<a href="http" target="_blank">http</a> import HttpResponse
import django_rq
from django.http import HttpResponse
from django.urls import path
from django_rq import get_queue
from netbox_proxbox.proxbox_api.plugins_config import QUEUE_NAME
from netbox_proxbox.queue_worker import start_sync

from .views import (
    ProxmoxVMCreateView,
    ProxmoxVMDeleteView,
    ProxmoxVMEditView,
    ProxmoxVMListView,
    ProxmoxVMView,
)

from netbox_proxbox import proxbox_api
import json


# This function is located on the wrong place
# Lately, it will have it's own template to display full update result
def full_update_view(request):
    update_all_result = proxbox_api.update.all(remove_unused=True)
    update_all_json = json.dumps(update_all_result, indent=4)

    '''
    remove_all_result = proxbox_api.remove.all()
    remove_all_json = json.dumps(remove_all_result, indent= 4)
    '''

    # html = "<html><body><h1>Update all Proxmox information</h1>{}<br><h1>Remove all useless information (like deleted VMs)</h1>{}</body></html>".format(update_all_json, remove_all_json)
    html = "<html><body><h1>Sync Netbox information based on Proxmox, updating and removing data.</h1>{}".format(
        update_all_json)
    return HttpResponse(html)


def start_sync_request(request):
    # queue = django_rq.get_queue(QUEUE_NAME)

    # queue.enqueue(start_sync, None, request.)
    queue = get_queue(QUEUE_NAME)
    queue_job = queue.enqueue_job(
        queue.create_job(
            func=start_sync,
            args=[None, request.user.username, True],
        )
    )
    print('Job queue')
    # queue = get_queue(QUEUE_NAME)
    # queue_job = queue.enqueue_job(
    #     start_sync,
    #     args=(None, request.user.username, True)
    # )
    # queue_job = start_sync.delay(None, request.user.username)
    # html = "<html><body><h1>Update all Proxmox information</h1>{}<br><h1>Remove all useless information (like deleted VMs)</h1>{}</body></html>".format(update_all_json, remove_all_json)
    html = "<html><body><h1>Sync Netbox information based on Proxmox, updating and removing data.</h1><br> queue job id{}".format(
        queue_job.id)
    return HttpResponse(html)


urlpatterns = [
    path("", ProxmoxVMListView.as_view(), name="proxmoxvm_list"),
    # <int:pk> = plugins/netbox_proxmoxvm/<pk> | example: plugins/netbox_proxmoxvm/1/
    # ProxmoxVMView.as_view() - as.view() is need so that our view class can process requests.
    # as_view() takes request and returns well-formed response, that is a class based view.
    path("<int:pk>/", ProxmoxVMView.as_view(), name="proxmoxvm"),
    path("add/", ProxmoxVMCreateView.as_view(), name="proxmoxvm_add"),
    path("<int:pk>/delete/", ProxmoxVMDeleteView.as_view(), name="proxmoxvm_delete"),
    path("<int:pk>/edit/", ProxmoxVMEditView.as_view(), name="proxmoxvm_edit"),

    # Proxbox API full update
    # path("full_update/", ProxmoxVMFullUpdate.as_view(), name="proxmoxvm_full_update")
    path("full_update/", full_update_view, name="proxmoxvm_full_update"),
    path("queue/", start_sync_request, name="proxmoxvm_queue")
]
