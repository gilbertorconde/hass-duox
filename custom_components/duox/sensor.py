"""Sensor platform for Fermax Duox (WiFi signal strength, call/opening history)."""
from __future__ import annotations

import datetime
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DEVICE_MANUFACTURER,
    DOMAIN,
    HASS_DUOX_VERSION,
    SIGNAL_CALL_STARTED,
    SIGNAL_DOOR_OPENED,
)
from .coordinator import FermaxCoordinator
from .fermax_api import DeviceInfo as FermaxDeviceInfo, FermaxClient, Pairing

LOGGER = logging.getLogger(__name__)

SIGNAL_MAP: dict[int, str] = {
    0: "terrible",
    1: "bad",
    2: "weak",
    3: "good",
    4: "excellent",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][config.entry_id]
    coordinator: FermaxCoordinator = data["coordinator"]
    client: FermaxClient = data["client"]
    pairings: list[Pairing] = data["pairings"]
    has_fcm: bool = data.get("has_fcm", False)

    sensors: list[SensorEntity] = []
    for pairing in pairings:
        device_info: FermaxDeviceInfo = data["device_info"][pairing.device_id]
        sensors.append(
            DuoxWifiSensor(coordinator, pairing.device_id, device_info)
        )
        sensors.append(
            DuoxLastOpeningSensor(
                hass, config.entry_id, client, pairing.device_id, device_info
            )
        )
        if has_fcm:
            sensors.append(
                DuoxLastCallSensor(
                    hass, config.entry_id, client, pairing.device_id, device_info
                )
            )

    async_add_entities(sensors)


class DuoxWifiSensor(CoordinatorEntity[FermaxCoordinator], SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["terrible", "bad", "weak", "good", "excellent", "unknown"]
    _attr_translation_key = "wifi_signal"
    _attr_icon = "mdi:wifi"

    def __init__(
        self,
        coordinator: FermaxCoordinator,
        device_id: str,
        device_info: FermaxDeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._model = device_info.model
        self._attr_unique_id = f"{device_id}_wifi_signal".lower()
        self._attr_name = "Duox WiFi Signal"

    @property
    def native_value(self) -> str | None:
        info = self.coordinator.data.get(self._device_id)
        if info is None:
            return None
        return SIGNAL_MAP.get(info.wireless_signal, "unknown")

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{self._model} {self._device_id}",
            manufacturer=DEVICE_MANUFACTURER,
            model=self._model,
            sw_version=HASS_DUOX_VERSION,
        )


class _DuoxTimestampSensor(SensorEntity):
    """Base for event-driven timestamp sensors with extra attributes."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_should_poll = False

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
        self._attr_native_value: datetime.datetime | None = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    @staticmethod
    def _parse_dt(value: Any) -> datetime.datetime | None:
        if not value:
            return None
        if isinstance(value, datetime.datetime):
            return value
        parsed = dt_util.parse_datetime(str(value))
        if parsed and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{self._model} {self._device_id}",
            manufacturer=DEVICE_MANUFACTURER,
            model=self._model,
            sw_version=HASS_DUOX_VERSION,
        )


class DuoxLastCallSensor(_DuoxTimestampSensor):
    """Timestamp of the most recent doorbell call for this device."""

    _attr_icon = "mdi:phone-incoming"

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self._attr_unique_id = f"{self._device_id}_last_call".lower()
        self._attr_name = "Duox Last Call"

    async def async_added_to_hass(self) -> None:
        # Refresh whenever a call starts on any door of this device.
        for door in self._visible_doors():
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_CALL_STARTED.format(self._device_id, door),
                    self._handle_event,
                )
            )
        await self._async_refresh()

    def _visible_doors(self) -> list[str]:
        data = self._hass.data[DOMAIN][self._entry_id]
        for pairing in data["pairings"]:
            if pairing.device_id == self._device_id:
                return [d.name for d in pairing.access_doors if d.visible]
        return []

    @callback
    def _handle_event(self) -> None:
        self.hass.async_create_task(self._async_refresh())

    async def _async_refresh(self) -> None:
        gcm_token = self._hass.data[DOMAIN][self._entry_id].get("gcm_token")
        if not gcm_token:
            return
        try:
            registry = await self._client.async_get_call_registry(gcm_token)
        except Exception:
            LOGGER.debug("Failed to refresh last call sensor", exc_info=True)
            return

        entries = [
            e for e in registry
            if not e.get("deviceId") or e.get("deviceId") == self._device_id
        ]
        if not entries:
            return

        entries.sort(key=lambda e: str(e.get("callDate", "")), reverse=True)
        latest = entries[0]
        self._attr_native_value = self._parse_dt(latest.get("callDate"))
        self._attr_extra_state_attributes = {
            "call_id": latest.get("id", ""),
            "answered": latest.get("answered", False),
            "photo_id": latest.get("photoId"),
        }
        self.async_write_ha_state()


class DuoxLastOpeningSensor(_DuoxTimestampSensor):
    """Timestamp of the most recent door opening for this device."""

    _attr_icon = "mdi:door-open"

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self._attr_unique_id = f"{self._device_id}_last_opening".lower()
        self._attr_name = "Duox Last Opening"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DOOR_OPENED.format(self._device_id),
                self._handle_event,
            )
        )
        await self._async_refresh()

    @callback
    def _handle_event(self, *args: Any) -> None:
        self.hass.async_create_task(self._async_refresh())

    async def _async_refresh(self) -> None:
        try:
            records = await self._client.async_get_opening_history(self._device_id)
        except Exception:
            LOGGER.debug("Failed to refresh last opening sensor", exc_info=True)
            return

        if not records:
            return

        records.sort(key=lambda r: str(r.get("instant", "")), reverse=True)
        latest = records[0]
        self._attr_native_value = self._parse_dt(latest.get("instant"))
        self._attr_extra_state_attributes = {
            "user": latest.get("email", ""),
            "door": latest.get("accessName") or latest.get("accessType", ""),
            "guest_email": latest.get("guestEmail"),
        }
        self.async_write_ha_state()
