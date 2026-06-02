"""Event platform for Fermax Duox (doorbell ring, door opened, camera on)."""
from __future__ import annotations

from functools import partial
from typing import Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEVICE_MANUFACTURER,
    DOMAIN,
    HASS_DUOX_VERSION,
    SIGNAL_CALL_STARTED,
    SIGNAL_DOOR_OPENED,
    SIGNAL_DOORBELL_RING,
)
from .fermax_api import DeviceInfo as FermaxDeviceInfo, Pairing


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][config.entry_id]
    pairings: list[Pairing] = data["pairings"]
    has_fcm: bool = data.get("has_fcm", False)

    entities: list[EventEntity] = []
    for pairing in pairings:
        device_info: FermaxDeviceInfo = data["device_info"][pairing.device_id]
        visible_doors = [d.name for d in pairing.access_doors if d.visible]

        entities.append(
            DuoxDoorOpenedEvent(pairing.device_id, device_info)
        )

        if has_fcm:
            entities.append(
                DuoxDoorbellEvent(pairing.device_id, device_info, visible_doors)
            )
            entities.append(
                DuoxCameraOnEvent(pairing.device_id, device_info, visible_doors)
            )

    async_add_entities(entities)


class _DuoxEventBase(EventEntity):
    """Shared device-info plumbing for Duox event entities."""

    _attr_should_poll = False
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


class DuoxDoorbellEvent(_DuoxEventBase):
    """Fires when the doorbell rings."""

    _attr_device_class = EventDeviceClass.DOORBELL
    _attr_event_types = ["ring"]
    _attr_icon = "mdi:doorbell-video"

    def __init__(
        self,
        device_id: str,
        device_info: FermaxDeviceInfo,
        doors: list[str],
    ) -> None:
        self._device_id = device_id
        self._model = device_info.model
        self._doors = doors
        self._attr_unique_id = f"{device_id}_doorbell_event".lower()
        self._attr_name = "Duox Doorbell"

    async def async_added_to_hass(self) -> None:
        for door in self._doors:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_DOORBELL_RING.format(self._device_id, door),
                    partial(self._fire, door),
                )
            )

    @callback
    def _fire(self, door: str) -> None:
        self._trigger_event("ring", {"door": door})
        self.async_write_ha_state()


class DuoxCameraOnEvent(_DuoxEventBase):
    """Fires when the intercom starts streaming (call or auto-on)."""

    _attr_event_types = ["camera_on"]
    _attr_icon = "mdi:cctv"

    def __init__(
        self,
        device_id: str,
        device_info: FermaxDeviceInfo,
        doors: list[str],
    ) -> None:
        self._device_id = device_id
        self._model = device_info.model
        self._doors = doors
        self._attr_unique_id = f"{device_id}_camera_on_event".lower()
        self._attr_name = "Duox Camera On"

    async def async_added_to_hass(self) -> None:
        for door in self._doors:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_CALL_STARTED.format(self._device_id, door),
                    partial(self._fire, door),
                )
            )

    @callback
    def _fire(self, door: str) -> None:
        self._trigger_event("camera_on", {"door": door})
        self.async_write_ha_state()


class DuoxDoorOpenedEvent(_DuoxEventBase):
    """Fires when a door is opened from Home Assistant."""

    _attr_event_types = ["door_opened"]
    _attr_icon = "mdi:door-open"

    def __init__(
        self,
        device_id: str,
        device_info: FermaxDeviceInfo,
    ) -> None:
        self._device_id = device_id
        self._model = device_info.model
        self._attr_unique_id = f"{device_id}_door_opened_event".lower()
        self._attr_name = "Duox Door Opened"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DOOR_OPENED.format(self._device_id),
                self._fire,
            )
        )

    @callback
    def _fire(self, door: str | None = None) -> None:
        self._trigger_event("door_opened", {"door": door})
        self.async_write_ha_state()
