"""Constants for the Hermes Conversation integration."""

DOMAIN = "hermes_conversation"

CONF_BRIDGE_URL = "bridge_url"
CONF_BRIDGE_TOKEN = "bridge_token"
CONF_HERMES_PROFILE = "hermes_profile"
CONF_TIMEOUT = "timeout"
CONF_ROUTING_MODE = "routing_mode"

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8787"
DEFAULT_HERMES_PROFILE = "default"
DEFAULT_TIMEOUT = 30
DEFAULT_ROUTING_MODE = "hermes_only"

ROUTING_MODES = ["hermes_only", "local_first", "cascade", "classifier"]

BRIDGE_CONVERSATION_PATH = "/api/conversation"
HEALTH_PATH = "/health"
INFO_PATH = "/api/info"

MAX_TEXT_LENGTH = 4096
