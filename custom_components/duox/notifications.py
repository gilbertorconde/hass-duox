"""FCM notification listener for Fermax Duox doorbell events."""
from __future__ import annotations

import logging
from typing import Any

from firebase_messaging import FcmPushClient, FcmRegisterConfig

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    FCM_API_KEY,
    FCM_APP_ID,
    FCM_PROJECT_ID,
    FCM_SENDER_ID,
    SIGNAL_CALL_ENDED,
    SIGNAL_CALL_STARTED,
)
from .fermax_api import FermaxClient

LOGGER = logging.getLogger(__name__)

FCM_CREDENTIALS_STORAGE_VERSION = 1


class FermaxNotificationListener:
    """Listens for Fermax doorbell push notifications via FCM."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: FermaxClient,
        entry_id: str,
    ) -> None:
        self._hass = hass
        self._client = client
        self._entry_id = entry_id
        self._push_client: FcmPushClient | None = None
        self._store = Store(
            hass,
            FCM_CREDENTIALS_STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}.fcm_credentials",
        )

    async def async_start(self) -> None:
        """Register with FCM and start listening for notifications."""
        credentials = await self._store.async_load()

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
        )

        fcm_token = await self._push_client.checkin_or_register()
        LOGGER.debug("FCM token obtained: %s...", fcm_token[:20] if fcm_token else "None")

        try:
            await self._client.async_register_app_token(fcm_token, active=True)
            LOGGER.info("Registered FCM token with Fermax API")
        except Exception:
            LOGGER.exception("Failed to register FCM token with Fermax API")

        await self._push_client.start()
        LOGGER.info("FCM notification listener started")

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
