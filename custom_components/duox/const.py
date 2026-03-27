DOMAIN = "duox"

CONF_LOCK_STATE_RESET = "lockStateReset"

DEVICE_MANUFACTURER = "Fermax"
HASS_DUOX_VERSION = "0.11.0"

# Firebase Cloud Messaging credentials (extracted from Fermax DuoxMe APK)
FCM_SENDER_ID = "***REDACTED_SENDER_ID***"
FCM_API_KEY = "***REDACTED_API_KEY***"
FCM_APP_ID = "***REDACTED_APP_ID***"
FCM_PROJECT_ID = "fermax-blue"
FCM_PACKAGE_NAME = "com.fermax.blue.app"

SIGNAL_CALL_STARTED = "{}_call_started_{}"
SIGNAL_CALL_ENDED = "{}_call_ended"

SIGNALING_SERVER_URL = "http://signaling-pro-duoxme.fermax.io"

CARD_BASE_URL = "/duox/www/duox-intercom-card.js"
CARD_URL = f"{CARD_BASE_URL}?v={HASS_DUOX_VERSION}"

DEFAULT_PREVIEW_TIMEOUT = 29
DEFAULT_CONVERSATION_TIMEOUT = 90
