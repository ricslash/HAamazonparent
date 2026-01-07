"""Constants for Amazon Parent Dashboard integration."""
from datetime import timedelta

# Integration domain
DOMAIN = "amazonparent"
LOGGER_NAME = "amazonparent"

# Configuration
CONF_ADDON_URL = "addon_url"
CONF_USE_ADDON_API = "use_addon_api"
CONF_COOKIE_FILE = "cookie_file"
CONF_KEY_FILE = "key_file"

# Defaults
DEFAULT_ADDON_URL = "http://localhost:8100"
DEFAULT_COOKIE_FILE = "/share/amazonparent/cookies.enc"
DEFAULT_KEY_FILE = "/share/amazonparent/.key"
DEFAULT_UPDATE_INTERVAL = timedelta(seconds=60)

# API endpoints
API_BASE_URL = "https://www.amazon.com/parentdashboard/ajax"
API_GET_HOUSEHOLD = "/get-household"
API_GET_CHILD_DEVICES = "/get-child-devices"
API_GET_TIME_LIMITS = "/get-adjusted-time-limits"
API_SET_OFFSCREEN_TIME = "/set-offscreen-time"
API_SET_TIME_LIMIT = "/set-time-limit-v2"

# Device types
DEVICE_TYPE_ECHO = "echo"
DEVICE_TYPE_FIRE_TABLET = "fire_tablet"

# Platforms
PLATFORMS = ["sensor", "switch", "button"]

# Attributes
ATTR_CHILD_ID = "child_id"
ATTR_CHILD_NAME = "child_name"
ATTR_DEVICE_ID = "device_id"
ATTR_DEVICE_NAME = "device_name"
ATTR_DURATION = "duration"
ATTR_DIRECTED_IDS = "directed_ids"
