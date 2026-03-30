DOMAIN = "duox"

CONF_LOCK_STATE_RESET = "lockStateReset"

DEVICE_MANUFACTURER = "Fermax"
HASS_DUOX_VERSION = "0.11.1"

# Firebase Cloud Messaging credentials (obfuscated)
from base64 import b64decode as _b64d

_K = "duox-fermax-hass"


def _d(e: str) -> str:
    return "".join(chr(b ^ ord(_K[i % len(_K)])) for i, b in enumerate(_b64d(e)))


FCM_SENDER_ID = _d("XEJWShteVkVZVkka")
FCM_API_KEY = _d("JTwVGX4fJAJAI1VXIxMgBA8/HhF1CSZAJkwvbhEWO0scL1gsZhMW")
FCM_APP_ID = _d("VU9XTxRUU0peVkwaWVZJEgoRHRdEAl8QVQRLFApUQRVQFFhMGFQHS19XHklc")
FCM_PROJECT_ID = _d("AhAdFUweSBABFB0=")
FCM_PACKAGE_NAME = _d("BxoCVksDFx8MGVZPBBQWXQUFHw==")

SIGNAL_CALL_STARTED = "{}_call_started_{}"
SIGNAL_DOORBELL_RING = "{}_doorbell_ring_{}"
SIGNAL_CALL_ENDED = "{}_call_ended"
SIGNAL_CALL_ATTENDED = "{}_call_attended"

SIGNALING_SERVER_URL = "http://signaling-pro-duoxme.fermax.io"

CARD_BASE_URL = "/duox/www/duox-intercom-card.js"
CARD_URL = f"{CARD_BASE_URL}?v={HASS_DUOX_VERSION}"

DEFAULT_PREVIEW_TIMEOUT = 29
DEFAULT_CONVERSATION_TIMEOUT = 90
