"""Switch platform for Fermax Duox (notifications, DND, photo caller)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_MANUFACTURER, DOMAIN, HASS_DUOX_VERSION
from .fermax_api import DeviceInfo as FermaxDeviceInfo, FermaxClient, Pairing

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][config.entry_id]
    client: FermaxClient = data["client"]
    pairings: list[Pairing] = data["pairings"]
    has_fcm: bool = data.get("has_fcm", False)

    switches: list[SwitchEntity] = []
    for pairing in pairings:
        device_info: FermaxDeviceInfo = data["device_info"][pairing.device_id]

        switches.append(
            DuoxPhotoCallerSwitch(
                client, pairing.device_id, device_info
            )
        )

        if has_fcm:
            switches.append(
                DuoxNotificationsSwitch(
                    hass, config.entry_id, pairing.device_id, device_info
                )
            )
            switches.append(
                DuoxDndSwitch(
                    hass, config.entry_id, client, pairing.device_id, device_info
                )
            )

    async_add_entities(switches)


class _DuoxSwitchBase(SwitchEntity):
    """Shared device-info plumbing for Duox switches."""

    _device_id: str
    _model: str

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{self._model} {self._device_id}",
            manufacturer=DEVICE_MANUFACTURER,
            model=self._model,
            sw_version=HASS_DUOX_VERSION,
        )


class DuoxPhotoCallerSwitch(_DuoxSwitchBase):
    """Enable/disable the photo caller feature (optimistic)."""

    _attr_icon = "mdi:camera-account"

    def __init__(
        self,
        client: FermaxClient,
        device_id: str,
        device_info: FermaxDeviceInfo,
    ) -> None:
        self._client = client
        self._device_id = device_id
        self._model = device_info.model
        self._attr_unique_id = f"{device_id}_photo_caller".lower()
        self._attr_name = "Duox Photo Caller"
        self._attr_is_on = device_info.photocaller

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.async_set_photo_caller(self._device_id, True)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.async_set_photo_caller(self._device_id, False)
        self._attr_is_on = False
        self.async_write_ha_state()


class DuoxDndSwitch(_DuoxSwitchBase):
    """Do Not Disturb (mute) switch for a device."""

    _attr_icon = "mdi:bell-off"

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        client: FermaxClient,
        device_id: str,
        device_info: FermaxDeviceInfo,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._client = client
        self._device_id = device_id
        self._model = device_info.model
        self._attr_unique_id = f"{device_id}_dnd".lower()
        self._attr_name = "Duox Do Not Disturb"
        self._attr_is_on = False

    def _gcm_token(self) -> str | None:
        return self._hass.data[DOMAIN][self._entry_id].get("gcm_token")

    async def async_added_to_hass(self) -> None:
        token = self._gcm_token()
        if not token:
            return
        try:
            self._attr_is_on = await self._client.async_get_dnd_status(
                self._device_id, token
            )
        except Exception:
            LOGGER.debug("Failed to fetch DND status", exc_info=True)

    async def async_turn_on(self, **kwargs: Any) -> None:
        token = self._gcm_token()
        if not token:
            return
        await self._client.async_set_dnd(self._device_id, token, True)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        token = self._gcm_token()
        if not token:
            return
        await self._client.async_set_dnd(self._device_id, token, False)
        self._attr_is_on = False
        self.async_write_ha_state()


class DuoxNotificationsSwitch(_DuoxSwitchBase):
    """Start/stop the FCM doorbell notification listener."""

    _attr_icon = "mdi:bell-ring"
    _attr_entity_category = None

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        device_id: str,
        device_info: FermaxDeviceInfo,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._device_id = device_id
        self._model = device_info.model
        self._attr_unique_id = f"{device_id}_notifications".lower()
        self._attr_name = "Duox Notifications"

    def _listener(self) -> Any:
        return self._hass.data[DOMAIN][self._entry_id].get("notification_listener")

    @property
    def is_on(self) -> bool:
        listener = self._listener()
        return bool(listener and listener.is_running)

    async def async_turn_on(self, **kwargs: Any) -> None:
        listener = self._listener()
        if listener:
            await listener.async_start()
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        listener = self._listener()
        if listener:
            await listener.async_stop()
            self.async_write_ha_state()
