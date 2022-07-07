#!/bin/bash
/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqworker high default low netbox_proxbox.netbox_proxbox &
/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqworker high default low netbox_proxbox.netbox_proxbox &
/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqworker high default low netbox_proxbox.netbox_proxbox &
/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqworker high default low netbox_proxbox.netbox_proxbox &
/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqworker high default low netbox_proxbox.netbox_proxbox &

/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqscheduler high default low netbox_proxbox.netbox_proxbox
exec "$@"
