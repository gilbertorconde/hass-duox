"""FCM notification listener for Fermax Duox doorbell events.

Uses Android-style GCM registration (matching the real Fermax Blue app)
so that Fermax's push service recognises the token and delivers doorbell
ring / call-end notifications.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from aiohttp import ClientSession, ClientTimeout
from firebase_messaging import FcmPushClient, FcmRegisterConfig
from firebase_messaging.fcmregister import FcmRegister

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import dispatcher_send
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
)
from .fermax_api import FermaxClient

LOGGER = logging.getLogger(__name__)

FCM_CREDENTIALS_STORAGE_VERSION = 2

GCM_REGISTER_URL = "https://android.clients.google.com/c2dm/register3"


def _build_package_cert() -> str:
    """Build a synthetic package certificate (mirrors bluecon's approach)."""
    sha = hashlib.sha512()
    sha.update(FCM_SENDER_ID.encode())
    sha.update(FCM_APP_ID.encode())
    sha.update(FCM_API_KEY.encode())
    sha.update(FCM_PROJECT_ID.encode())
    sha.update(FCM_PACKAGE_NAME.encode())
    return sha.hexdigest()


async def _android_gcm_register(
    session: ClientSession,
    android_id: int,
    security_token: int,
    retries: int = 5,
) -> str | None:
    """Register with GCM as the Fermax Android app and return the GCM token."""
    package_cert = _build_package_cert()
    headers = {
        "Authorization": f"AidLogin {android_id}:{security_token}",
        "Content-Type": "application/x-www-form-urlencoded",
        "app": FCM_PACKAGE_NAME,
    }
    body = {
        "app": FCM_PACKAGE_NAME,
        "X-subtype": FCM_SENDER_ID,
        "sender": FCM_SENDER_ID,
        "device": str(android_id),
        "cert": package_cert,
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
                        "Android GCM register attempt %d/%d failed: %s",
                        attempt + 1,
                        retries,
                        text,
                    )
                    last_error = text
                    continue
                token = text.split("=")[1]
                LOGGER.debug("Android GCM token obtained")
                return token
        except Exception as exc:
            last_error = exc
            LOGGER.warning(
                "Android GCM register attempt %d/%d error",
                attempt + 1,
                retries,
                exc_info=True,
            )

    LOGGER.error("Android GCM registration failed after %d attempts: %s", retries, last_error)
    return None


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
        credentials = await self._store.async_load()

        if not credentials:
            LOGGER.info("No FCM credentials stored – performing Android registration")
            credentials = await self._register_android()
            if not credentials:
                raise RuntimeError("Failed to register with FCM")
            await self._store.async_save(credentials)

        def on_credentials_updated(creds: dict) -> None:
            self._hass.async_create_task(self._store.async_save(creds))

        fcm_config = FcmRegisterConfig(
            FCM_PROJECT_ID,
            FCM_APP_ID,
            FCM_API_KEY,
            FCM_SENDER_ID,
        )

        self._push_client = FcmPushClient(
            self._on_notification,
            fcm_config,
            credentials,
            on_credentials_updated,
            http_client_session=self._session,
        )

        fcm_token = await self._push_client.checkin_or_register()
        LOGGER.debug(
            "FCM token: %s...", fcm_token[:20] if fcm_token else "None"
        )

        try:
            await self._client.async_register_app_token(fcm_token, active=True)
            LOGGER.info("Registered FCM token with Fermax API")
        except Exception:
            LOGGER.exception("Failed to register FCM token with Fermax API")

        await self._push_client.start()
        LOGGER.info("FCM notification listener started")

    async def _register_android(self) -> dict[str, Any] | None:
        """Perform a full Android-style FCM registration.

        1. GCM check-in  (standard, for android_id / security_token)
        2. GCM register  (Android-style: package name + cert + sender_id)
        3. Generate ECDH keys
        4. FCM install + register (web-push subscription for encryption)
        """
        fcm_config = FcmRegisterConfig(
            FCM_PROJECT_ID,
            FCM_APP_ID,
            FCM_API_KEY,
            FCM_SENDER_ID,
        )

        helper = FcmRegister(
            fcm_config,
            None,
            None,
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
                self._session, android_id, security_token
            )
            if not gcm_token:
                return None

            gcm_data = {
                "token": gcm_token,
                "app_id": FCM_APP_ID,
                "android_id": android_id,
                "security_token": security_token,
            }

            keys = helper.generate_keys()

            fcm_data = await helper.fcm_install_and_register(gcm_data, keys)
            if not fcm_data:
                LOGGER.error("FCM install/register failed")
                return None

            credentials: dict[str, Any] = {
                "keys": keys,
                "gcm": gcm_data,
                "fcm": fcm_data,
                "config": {
                    "bundle_id": fcm_config.bundle_id,
                    "project_id": fcm_config.project_id,
                    "vapid_key": fcm_config.vapid_key,
                },
            }
            LOGGER.info("Android FCM registration completed")
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

        notif_type = notification.get("FermaxNotificationType")
        device_id = notification.get("DeviceId")

        if not notif_type or not device_id:
            LOGGER.debug("Ignoring non-Fermax notification: %s", notification)
            return

        if notif_type == "Call":
            access_door_key = notification.get("AccessDoorKey", "")
            fcm_message_id = persistent_id
            LOGGER.info(
                "Doorbell ring: device=%s door=%s", device_id, access_door_key
            )
            dispatcher_send(
                self._hass,
                SIGNAL_CALL_STARTED.format(device_id, access_door_key),
            )
            self._hass.bus.fire(
                f"{DOMAIN}_doorbell_ring",
                {"device_id": device_id, "access_door_key": access_door_key},
            )

            if notification.get("SendAcknowledge"):
                self._hass.async_create_task(
                    self._client.async_acknowledge_notification(fcm_message_id)
                )

        elif notif_type == "CallEnd":
            LOGGER.info("Call ended: device=%s", device_id)
            dispatcher_send(
                self._hass,
                SIGNAL_CALL_ENDED.format(device_id),
            )
        else:
            LOGGER.debug("Unknown notification type: %s", notif_type)
