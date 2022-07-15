import pytz
import logging
import os
from pathlib import Path

# Default Plugins settings
from netbox_proxbox import ProxboxConfig
from netbox.settings import PLUGINS_CONFIG

from datetime import datetime
from django.conf import settings

DEFAULT_PLUGINS_CONFIG = ProxboxConfig.default_settings
DEFAULT_NETBOX_PROXBOX_LOG_FILE = DEFAULT_PLUGINS_CONFIG.get("NETBOX_PROXBOX_LOG_FILE")

USER_PLUGINS_CONFIG = PLUGINS_CONFIG.get("netbox_proxbox")
NETBOX_PROXBOX_LOG_FILE = USER_PLUGINS_CONFIG.get("NETBOX_PROXBOX_LOG_FILE", DEFAULT_NETBOX_PROXBOX_LOG_FILE)
TIME_ZONE = os.environ.get('TIME_ZONE', 'UTC')

try:
    file = Path(NETBOX_PROXBOX_LOG_FILE)
    file.touch(exist_ok=True)
    file = open(NETBOX_PROXBOX_LOG_FILE, 'r')
except Exception as e:
    print("Error: logger-path - {}".format(e.message))
    file = open(NETBOX_PROXBOX_LOG_FILE, 'w')


def CustomTimeZone(*args):
    utc_dt = pytz.utc.localize(datetime.utcnow())
    my_tz = pytz.timezone(TIME_ZONE)
    converted = utc_dt.astimezone(my_tz)
    return converted.timetuple()


log_f = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    '%Y-%m-%d %H:%M:%S'
)
log_fh = logging.FileHandler(NETBOX_PROXBOX_LOG_FILE)
log_fh.setFormatter(log_f)
log_fh.formatter.converter = CustomTimeZone
log = logging.getLogger('netbox-proxbox')
log.setLevel(logging.INFO)
log.addHandler(log_fh)
