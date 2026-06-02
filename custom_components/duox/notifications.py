"""FCM notification listener for Fermax Duox doorbell events.

Replicates the exact registration flow from the ``rustPlusPushReceiver``
library's ``AndroidFCM`` class that the original bluecon library uses:

1. Firebase Installation  (with X-Android-Package / X-Android-Cert headers)
2. GCM check-in
3. GCM register           (with Firebase Installations Auth token)
4. Register the raw GCM token with Fermax

The ``firebase-messaging`` library is used only for the MCS persistent
connection that receives push messages from Google.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import secrets
import time
from base64 import b64encode
from collections import deque
from datetime import timedelta
from typing import Any

from aiohttp import ClientSession, ClientTimeout
from firebase_messaging import FcmPushClient, FcmRegisterConfig
from firebase_messaging.fcmregister import FcmRegister

try:  # FcmPushClientConfig may live in different modules across versions.
    from firebase_messaging import FcmPushClientConfig
except ImportError:  # pragma: no cover - fallback for older library layouts
    try:
        from firebase_messaging.fcmpushclient import FcmPushClientConfig
    except ImportError:
        FcmPushClientConfig = None  # type: ignore[assignment,misc]

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import (
    CONF_SIGNALING_URL,
    DOMAIN,
    FCM_API_KEY,
    FCM_APP_ID,
    FCM_PACKAGE_NAME,
    FCM_PROJECT_ID,
    FCM_SENDER_ID,
    SIGNAL_CALL_ATTENDED,
    SIGNAL_CALL_ENDED,
    SIGNAL_CALL_STARTED,
    SIGNAL_DOORBELL_RING,
    SIGNALING_SERVER_URL,
)
from .fermax_api import FermaxClient

LOGGER = logging.getLogger(__name__)

FCM_CREDENTIALS_STORAGE_VERSION = 4
_SENSITIVE_HINTS = ("token", "auth", "secret", "password", "key")

# Periodically verify the push connection is alive and restart it if not.
FCM_WATCHDOG_INTERVAL = timedelta(seconds=60)
# Suppress ring-type notifications briefly after (re)connect: FCM replays
# undelivered messages on connect, which would otherwise fire phantom rings.
STARTUP_GRACE_PERIOD = 10.0
# Number of recently-seen FCM message IDs kept to drop duplicate deliveries.
SEEN_IDS_MAXLEN = 100

GCM_REGISTER_URL = "https://android.clients.google.com/c2dm/register3"
FIREBASE_INSTALL_URL = (
    "https://firebaseinstallations.googleapis.com/v1/"
    f"projects/{FCM_PROJECT_ID}/installations"
)
FIREBASE_CLIENT_HEADER = (
    "android-min-sdk/23 fire-core/20.0.0 device-name/a21snnxx "
    "device-brand/samsung device-model/a21s "
    "android-installer/com.android.vending fire-android/30 "
    "fire-installations/17.0.0 fire-fcm/22.0.0 android-platform/ "
    "kotlin/1.9.23 android-target-sdk/34"
)


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return payload copy with sensitive values redacted for logs."""
    redacted: dict[str, Any] = {}
    for key in sorted(payload):
        value = payload.get(key)
        key_l = key.lower()
        if any(hint in key_l for hint in _SENSITIVE_HINTS):
            if isinstance(value, str) and len(value) > 10:
                redacted[key] = f"{value[:4]}...{value[-4:]}"
            elif value is None:
                redacted[key] = None
            else:
                redacted[key] = "[redacted]"
            continue

        if isinstance(value, str) and len(value) > 300:
            redacted[key] = f"{value[:120]}...[truncated]...{value[-40:]}"
        else:
            redacted[key] = value
    return redacted


def _build_package_cert() -> str:
    """Build a synthetic package certificate (mirrors bluecon's approach)."""
    sha = hashlib.sha512()
    sha.update(FCM_SENDER_ID.encode())
    sha.update(FCM_APP_ID.encode())
    sha.update(FCM_API_KEY.encode())
    sha.update(FCM_PROJECT_ID.encode())
    sha.update(FCM_PACKAGE_NAME.encode())
    return sha.hexdigest()


def _generate_fid() -> str:
    """Generate a Firebase Installation ID (17 random bytes, FID header)."""
    fid = bytearray(secrets.token_bytes(17))
    fid[0] = 0b01110000 + (fid[0] % 0b00010000)
    return b64encode(fid).decode()


async def _firebase_install(session: ClientSession, package_cert: str) -> str:
    """Create a Firebase Installation and return the auth token."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Android-Package": FCM_PACKAGE_NAME,
        "X-Android-Cert": package_cert,
        "x-firebase-client": FIREBASE_CLIENT_HEADER,
        "x-firebase-client-log-type": "3",
        "x-goog-api-key": FCM_API_KEY,
        "User-Agent": (
            "Dalvik/2.1.0 (Linux; U; Android 11; "
            "SM-A217F Build/RP1A.200720.012)"
        ),
    }
    body = {
        "fid": _generate_fid(),
        "appId": FCM_APP_ID,
        "authVersion": "FIS_v2",
        "sdkVersion": "a:17.0.0",
    }

    async with session.post(
        url=FIREBASE_INSTALL_URL,
        headers=headers,
        json=body,
        timeout=ClientTimeout(total=10),
    ) as resp:
        data = await resp.json()

    auth_token = (data.get("authToken") or {}).get("token")
    if not auth_token:
        raise RuntimeError(f"Firebase installation failed: {data}")
    LOGGER.info("Firebase installation auth token obtained")
    return auth_token


async def _android_gcm_register(
    session: ClientSession,
    android_id: int,
    security_token: int,
    installation_auth_token: str,
    package_cert: str,
    retries: int = 5,
) -> str | None:
    """Register with GCM as the Fermax Android app and return the GCM token."""
    headers = {
        "Authorization": f"AidLogin {android_id}:{security_token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = {
        "device": str(android_id),
        "app": FCM_PACKAGE_NAME,
        "cert": package_cert,
        "app_ver": "1",
        "X-subtype": FCM_SENDER_ID,
        "X-app_ver": "1",
        "X-osv": "29",
        "X-cliv": "fiid-21.1.1",
        "X-gmsv": "220217001",
        "X-scope": "*",
        "X-Goog-Firebase-Installations-Auth": installation_auth_token,
        "X-gms_app_id": FCM_APP_ID,
        "X-Firebase-Client": FIREBASE_CLIENT_HEADER,
        "X-Firebase-Client-Log-Type": "1",
        "X-app_ver_name": "1",
        "target_ver": "31",
        "sender": FCM_SENDER_ID,
    }

    last_error: str | Exception | None = None
    for attempt in range(retries):
        try:
            async with session.post(
                url=GCM_REGISTER_URL,
                headers=headers,
                data=body,
                timeout=ClientTimeout(total=5),
            ) as resp:
                text = await resp.text()
                if "Error" in text:
                    LOGGER.warning(
                        "GCM register attempt %d/%d failed: %s",
                        attempt + 1,
                        retries,
                        text,
                    )
                    last_error = text
                    continue
                token = text.split("=")[1]
                LOGGER.info("Android GCM token obtained")
                return token
        except Exception as exc:
            last_error = exc
            LOGGER.warning(
                "GCM register attempt %d/%d error",
                attempt + 1,
                retries,
                exc_info=True,
            )

    LOGGER.error(
        "GCM registration failed after %d attempts: %s", retries, last_error
    )
    return None


class AndroidFcmPushClient(FcmPushClient):
    """FcmPushClient that handles unencrypted Android-style FCM messages.

    The base class assumes web-push encryption (``crypto-key`` header).
    Android GCM registrations receive plain-text data messages where the
    notification payload lives directly in the protobuf ``app_data`` field.
    """

    def _handle_data_message(self, msg: Any) -> None:
        try:
            self._app_data_by_key(msg, "crypto-key")
        except RuntimeError:
            notification: dict[str, str] = {}
            for item in msg.app_data:
                notification[item.key] = item.value
            persistent_id: str = msg.persistent_id
            LOGGER.debug("Android FCM data message: %s", notification)
            self.callback(notification, persistent_id, None)
            return

        super()._handle_data_message(msg)


class FermaxNotificationListener:
    """Listens for Fermax doorbell push notifications via FCM."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: FermaxClient,
        entry_id: str,
        session: ClientSession,
    ) -> None:
        self._hass = hass
        self._client = client
        self._entry_id = entry_id
        self._session = session
        self._push_client: FcmPushClient | None = None
        self._store = Store(
            hass,
            FCM_CREDENTIALS_STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}.fcm_credentials",
        )
        # Reused across restarts so we don't re-arm dedup on every reconnect.
        self._seen_ids: deque[str] = deque(maxlen=SEEN_IDS_MAXLEN)
        self._start_lock = asyncio.Lock()
        self._credentials: dict[str, Any] | None = None
        self._gcm_token: str | None = None
        self._started_at: float | None = None
        self._watchdog_cancel: Any = None

    @property
    def is_running(self) -> bool:
        """Return True if the push client appears to be connected."""
        return self._is_client_running()

    def _default_socket_url(self) -> str:
        """Return the signaling URL, honoring any configured override."""
        entry = self._hass.config_entries.async_get_entry(self._entry_id)
        if entry is not None:
            return entry.options.get(CONF_SIGNALING_URL) or SIGNALING_SERVER_URL
        return SIGNALING_SERVER_URL

    def _is_client_running(self) -> bool:
        client = self._push_client
        if client is None:
            return False
        is_started = getattr(client, "is_started", None)
        if isinstance(is_started, bool):
            return is_started
        run_state = getattr(client, "_run_state", None)
        if run_state is not None:
            name = getattr(run_state, "name", str(run_state)).upper()
            return name in ("STARTED", "STARTING")
        # Unknown library internals: assume running to avoid restart loops.
        return True

    async def async_start(self) -> None:
        """Register with FCM, start listening, and arm the watchdog."""
        await self._ensure_running()
        if self._watchdog_cancel is None:
            self._watchdog_cancel = async_track_time_interval(
                self._hass, self._watchdog_tick, FCM_WATCHDOG_INTERVAL
            )

    async def _watchdog_tick(self, _now: Any) -> None:
        """Periodic check that restarts the listener if it died."""
        try:
            await self.ensure_running()
        except Exception:
            LOGGER.exception("FCM watchdog failed to restore the listener")

    async def ensure_running(self) -> None:
        """Restart the push client if it is no longer running."""
        if self._is_client_running():
            return
        async with self._start_lock:
            if self._is_client_running():
                return
            LOGGER.warning("FCM listener not running; restarting")
            await self._ensure_running()

    async def _ensure_running(self) -> None:
        """(Re)start the FCM push client, registering credentials if needed."""
        if self._push_client is not None:
            try:
                await self._push_client.stop()
            except Exception:
                LOGGER.debug("Error stopping previous FCM client", exc_info=True)
            self._push_client = None

        credentials = self._credentials
        if credentials is None:
            try:
                credentials = await self._store.async_load()
            except NotImplementedError:
                LOGGER.warning(
                    "Stored FCM credentials are from an older version, "
                    "re-registering"
                )
                credentials = None

            if not credentials:
                LOGGER.info("No FCM credentials — performing Android registration")
                credentials = await self._register_android()
                if not credentials:
                    raise RuntimeError("Failed to register with GCM")
                await self._store.async_save(credentials)
            self._credentials = credentials

        gcm_token = credentials["gcm"]["token"]
        self._gcm_token = gcm_token
        self._hass.data[DOMAIN][self._entry_id]["gcm_token"] = gcm_token

        def on_credentials_updated(creds: dict) -> None:
            self._credentials = creds
            self._hass.async_create_task(self._store.async_save(creds))

        fcm_config = FcmRegisterConfig(
            FCM_PROJECT_ID,
            FCM_APP_ID,
            FCM_API_KEY,
            FCM_SENDER_ID,
        )

        client_kwargs: dict[str, Any] = {
            "http_client_session": self._session,
            "received_persistent_ids": list(self._seen_ids),
        }
        if FcmPushClientConfig is not None:
            # Keep retrying forever instead of permanently aborting; the
            # watchdog is a backstop on top of this.
            try:
                client_kwargs["config"] = FcmPushClientConfig(
                    abort_on_sequential_error_count=None
                )
            except TypeError:
                LOGGER.debug(
                    "FcmPushClientConfig signature mismatch; using defaults"
                )

        # Only pass kwargs the installed library actually accepts, so version
        # differences cannot break listener startup with a TypeError.
        try:
            accepted = set(
                inspect.signature(AndroidFcmPushClient.__init__).parameters
            )
            client_kwargs = {
                k: v for k, v in client_kwargs.items() if k in accepted
            }
        except (ValueError, TypeError):
            pass

        self._push_client = AndroidFcmPushClient(
            self._on_notification,
            fcm_config,
            credentials,
            on_credentials_updated,
            **client_kwargs,
        )

        await self._push_client.checkin_or_register()

        try:
            await self._client.async_register_app_token(gcm_token, active=True)
            LOGGER.info("Registered GCM token with Fermax API")
        except Exception:
            LOGGER.exception("Failed to register GCM token with Fermax API")

        await self._push_client.start()
        self._started_at = time.monotonic()
        LOGGER.info("FCM notification listener started")

    async def _register_android(self) -> dict[str, Any] | None:
        """Replicate AndroidFCM.register() from rustPlusPushReceiver.

        1. Firebase Installation  (with Android package/cert headers)
        2. GCM check-in           (for android_id + security_token)
        3. GCM register           (with installation auth + Android params)

        Returns credentials dict compatible with firebase-messaging's
        FcmPushClient (needs gcm.android_id and gcm.security_token for
        the MCS connection).
        """
        package_cert = _build_package_cert()

        try:
            install_token = await _firebase_install(
                self._session, package_cert
            )
        except Exception:
            LOGGER.exception("Firebase installation failed")
            return None

        fcm_config = FcmRegisterConfig(
            FCM_PROJECT_ID,
            FCM_APP_ID,
            FCM_API_KEY,
            FCM_SENDER_ID,
        )
        helper = FcmRegister(
            fcm_config, None, None,
            http_client_session=self._session,
        )

        try:
            options = await helper.gcm_check_in()
            if not options:
                LOGGER.error("GCM check-in failed")
                return None

            android_id = options["androidId"]
            security_token = options["securityToken"]

            gcm_token = await _android_gcm_register(
                self._session,
                android_id,
                security_token,
                install_token,
                package_cert,
            )
            if not gcm_token:
                return None

            keys = helper.generate_keys()

            credentials: dict[str, Any] = {
                "keys": keys,
                "gcm": {
                    "token": gcm_token,
                    "app_id": FCM_APP_ID,
                    "android_id": android_id,
                    "security_token": security_token,
                },
                "fcm": {
                    "registration": {"token": gcm_token},
                    "installation": None,
                },
                "config": {
                    "bundle_id": fcm_config.bundle_id,
                    "project_id": fcm_config.project_id,
                    "vapid_key": fcm_config.vapid_key,
                },
            }
            LOGGER.info("Android GCM registration completed")
            return credentials
        finally:
            await helper.close()

    async def async_stop(self) -> None:
        """Stop the watchdog, stop listening, and unregister the token."""
        if self._watchdog_cancel is not None:
            self._watchdog_cancel()
            self._watchdog_cancel = None

        if self._push_client:
            await self._push_client.stop()
            self._push_client = None
            LOGGER.info("FCM notification listener stopped")

        if self._gcm_token:
            try:
                await self._client.async_register_app_token(
                    self._gcm_token, active=False
                )
                LOGGER.info("Unregistered GCM token with Fermax API")
            except Exception:
                LOGGER.debug(
                    "Failed to unregister GCM token with Fermax API",
                    exc_info=True,
                )

    def _on_notification(
        self,
        notification: dict[str, Any],
        persistent_id: str,
        obj: Any = None,
    ) -> None:
        """Handle incoming FCM notification."""
        notif_type = notification.get("FermaxNotificationType")
        device_id = notification.get("DeviceId")

        if not notif_type or not device_id:
            LOGGER.debug(
                "Ignoring non-Fermax notification keys=%s",
                sorted(notification.keys()),
            )
            return

        # Drop duplicate deliveries (FCM replays unacked messages on reconnect).
        if persistent_id:
            if persistent_id in self._seen_ids:
                LOGGER.debug(
                    "Ignoring duplicate FCM message persistent_id=%s", persistent_id
                )
                return
            self._seen_ids.append(persistent_id)

        # During the grace window after (re)connect, suppress ring-type
        # notifications that FCM may replay from its backlog.
        in_grace = (
            self._started_at is not None
            and (time.monotonic() - self._started_at) < STARTUP_GRACE_PERIOD
        )
        if in_grace and notif_type in ("Call", "Autoon"):
            LOGGER.info(
                "Suppressing %s notification during startup grace period "
                "(device=%s)",
                notif_type,
                device_id,
            )
            return

        LOGGER.info(
            "Fermax FCM received type=%s device=%s keys=%s",
            notif_type,
            device_id,
            sorted(notification.keys()),
        )
        LOGGER.debug("Fermax FCM payload: %s", _redact_payload(notification))

        access_door_key = notification.get("AccessDoorKey", "")
        call_as = notification.get("CallAs", "")
        room_id = notification.get("RoomId", "")

        base_event_data = {
            "device_id": device_id,
            "access_door_key": access_door_key,
            "call_as": call_as,
            "room_id": room_id,
            "notification_type": notif_type,
            "title": notification.get("NotificationTitle", ""),
            "body": notification.get("NotificationBody", ""),
            "title_key": notification.get("NotificationTitleLocKey", ""),
            "body_key": notification.get("NotificationBodyLocKey", ""),
        }

        if notif_type in ("Call", "Autoon"):
            LOGGER.info("Incoming %s — device=%s door=%s", notif_type, device_id, access_door_key)

            call_data = {
                **base_event_data,
                "socket_url": notification.get("SocketUrl", self._default_socket_url()),
                "streaming_mode": notification.get("StreamingMode", ""),
                "fermax_token": notification.get("FermaxToken", ""),
                "preview_timeout": int(notification.get("PreviewTimeout", "29")),
                "conversation_timeout": int(notification.get("ConversationTimeout", "90")),
            }

            self._hass.data[DOMAIN][self._entry_id]["active_call"] = call_data

            async_dispatcher_send(
                self._hass,
                SIGNAL_CALL_STARTED.format(device_id, access_door_key),
            )

            if notif_type == "Call":
                self._hass.bus.async_fire(f"{DOMAIN}_doorbell_ring", base_event_data)
                async_dispatcher_send(
                    self._hass,
                    SIGNAL_DOORBELL_RING.format(device_id, access_door_key),
                )

            self._hass.bus.async_fire(f"{DOMAIN}_incoming_call", call_data)

            if notification.get("SendAcknowledge"):
                self._hass.async_create_task(
                    self._client.async_acknowledge_notification(persistent_id)
                )

        elif notif_type == "CallAttend":
            LOGGER.info("Call attended by another device: device=%s", device_id)
            self._hass.data[DOMAIN][self._entry_id]["active_call"] = None

            async_dispatcher_send(
                self._hass,
                SIGNAL_CALL_ATTENDED.format(device_id),
            )
            async_dispatcher_send(
                self._hass,
                SIGNAL_CALL_ENDED.format(device_id),
            )
            self._hass.bus.async_fire(f"{DOMAIN}_call_attended", base_event_data)

            if notification.get("SendAcknowledge"):
                self._hass.async_create_task(
                    self._client.async_acknowledge_notification(persistent_id)
                )

        elif notif_type == "CallEnd":
            LOGGER.info("Call ended: device=%s", device_id)
            self._hass.data[DOMAIN][self._entry_id]["active_call"] = None

            async_dispatcher_send(
                self._hass,
                SIGNAL_CALL_ENDED.format(device_id),
            )
            self._hass.bus.async_fire(f"{DOMAIN}_call_ended", base_event_data)

            if notification.get("SendAcknowledge"):
                self._hass.async_create_task(
                    self._client.async_acknowledge_notification(persistent_id)
                )

        elif notif_type == "ChangeVideoSource":
            LOGGER.info("Video source change: device=%s", device_id)
            self._hass.bus.async_fire(f"{DOMAIN}_change_video", base_event_data)

        elif notif_type == "Info":
            title = notification.get("NotificationTitle", "")
            body = notification.get("NotificationBody", "")
            LOGGER.info("Info notification: %s — %s", title, body)
            self._hass.bus.async_fire(f"{DOMAIN}_info", {
                **base_event_data,
                "title": title,
                "body": body,
            })

        elif notif_type == "FwUpdate":
            LOGGER.info("Firmware update available: device=%s", device_id)
            self._hass.bus.async_fire(f"{DOMAIN}_fw_update", base_event_data)

        elif notif_type == "Logout":
            LOGGER.warning("Logout notification received: device=%s", device_id)
            self._hass.bus.async_fire(f"{DOMAIN}_logout", base_event_data)

        else:
            LOGGER.debug("Unhandled notification type: %s — %s", notif_type, notification)
