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

import hashlib
import logging
import secrets
from base64 import b64encode
from typing import Any

from aiohttp import ClientSession, ClientTimeout
from firebase_messaging import FcmPushClient, FcmRegisterConfig
from firebase_messaging.fcmregister import FcmRegister

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    FCM_API_KEY,
    FCM_APP_ID,
    FCM_PACKAGE_NAME,
    FCM_PROJECT_ID,
    FCM_SENDER_ID,
    SIGNAL_CALL_ENDED,
    SIGNAL_CALL_STARTED,
    SIGNALING_SERVER_URL,
)
from .fermax_api import FermaxClient

LOGGER = logging.getLogger(__name__)

FCM_CREDENTIALS_STORAGE_VERSION = 4

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

    async def async_start(self) -> None:
        """Register with FCM and start listening for notifications."""
        try:
            credentials = await self._store.async_load()
        except NotImplementedError:
            LOGGER.warning(
                "Stored FCM credentials are from an older version, re-registering"
            )
            credentials = None

        if not credentials:
            LOGGER.info("No FCM credentials — performing Android registration")
            credentials = await self._register_android()
            if not credentials:
                raise RuntimeError("Failed to register with GCM")
            await self._store.async_save(credentials)

        gcm_token = credentials["gcm"]["token"]

        self._hass.data[DOMAIN][self._entry_id]["gcm_token"] = gcm_token

        def on_credentials_updated(creds: dict) -> None:
            self._hass.async_create_task(self._store.async_save(creds))

        fcm_config = FcmRegisterConfig(
            FCM_PROJECT_ID,
            FCM_APP_ID,
            FCM_API_KEY,
            FCM_SENDER_ID,
        )

        self._push_client = AndroidFcmPushClient(
            self._on_notification,
            fcm_config,
            credentials,
            on_credentials_updated,
            http_client_session=self._session,
        )

        await self._push_client.checkin_or_register()

        try:
            await self._client.async_register_app_token(gcm_token, active=True)
            LOGGER.info("Registered GCM token with Fermax API")
        except Exception:
            LOGGER.exception("Failed to register GCM token with Fermax API")

        await self._push_client.start()
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
        """Stop listening and unregister."""
        if self._push_client:
            await self._push_client.stop()
            LOGGER.info("FCM notification listener stopped")

    def _on_notification(
        self,
        notification: dict[str, Any],
        persistent_id: str,
        obj: Any = None,
    ) -> None:
        """Handle incoming FCM notification."""
        LOGGER.debug("FCM notification received: %s", notification)
        LOGGER.debug("FCM notification keys: %s", list(notification.keys()))

        notif_type = notification.get("FermaxNotificationType")
        device_id = notification.get("DeviceId")

        if not notif_type or not device_id:
            LOGGER.debug("Ignoring non-Fermax notification: %s", notification)
            return

        if notif_type == "Call":
            LOGGER.info(
                "Incoming call — raw FCM data: %s", notification
            )
            access_door_key = notification.get("AccessDoorKey", "")
            fcm_message_id = persistent_id

            call_data = {
                "device_id": device_id,
                "access_door_key": access_door_key,
                "room_id": notification.get("RoomId", ""),
                "socket_url": notification.get(
                    "SocketUrl", SIGNALING_SERVER_URL
                ),
                "call_as": notification.get("CallAs", ""),
                "streaming_mode": notification.get("StreamingMode", ""),
                "fermax_token": notification.get("FermaxToken", ""),
                "preview_timeout": int(
                    notification.get("PreviewTimeout", "29")
                ),
                "conversation_timeout": int(
                    notification.get("ConversationTimeout", "90")
                ),
            }

            self._hass.data[DOMAIN][self._entry_id]["active_call"] = call_data

            LOGGER.info(
                "Doorbell ring: device=%s door=%s room=%s",
                device_id,
                access_door_key,
                call_data["room_id"],
            )
            async_dispatcher_send(
                self._hass,
                SIGNAL_CALL_STARTED.format(device_id, access_door_key),
            )
            self._hass.bus.async_fire(
                f"{DOMAIN}_doorbell_ring",
                {"device_id": device_id, "access_door_key": access_door_key},
            )
            self._hass.bus.async_fire(
                f"{DOMAIN}_incoming_call",
                call_data,
            )

            if notification.get("SendAcknowledge"):
                self._hass.async_create_task(
                    self._client.async_acknowledge_notification(fcm_message_id)
                )

        elif notif_type == "CallEnd":
            LOGGER.info("Call ended: device=%s", device_id)
            self._hass.data[DOMAIN][self._entry_id]["active_call"] = None
            async_dispatcher_send(
                self._hass,
                SIGNAL_CALL_ENDED.format(device_id),
            )
        else:
            LOGGER.debug("Unknown notification type: %s", notif_type)
