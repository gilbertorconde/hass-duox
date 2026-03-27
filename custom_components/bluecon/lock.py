"""Lock platform for Fermax Blue."""
from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LOCK_STATE_RESET, DEVICE_MANUFACTURER, DOMAIN, HASS_BLUECON_VERSION
from .fermax_api import AccessDoor, DeviceInfo as FermaxDeviceInfo, FermaxClient, Pairing


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: FermaxClient = hass.data[DOMAIN][config.entry_id]["client"]
    pairings: list[Pairing] = hass.data[DOMAIN][config.entry_id]["pairings"]
    lock_timeout = config.options.get(CONF_LOCK_STATE_RESET, 5)

    locks: list[BlueConLock] = []

    for pairing in pairings:
        device_info: FermaxDeviceInfo = hass.data[DOMAIN][config.entry_id][
            "device_info"
        ][pairing.device_id]

        for door in pairing.access_doors:
            if not door.visible:
                continue
            locks.append(
                BlueConLock(client, pairing.device_id, door, device_info, lock_timeout)
            )

    async_add_entities(locks)


class BlueConLock(LockEntity):
    _attr_should_poll = False

    def __init__(
        self,
        client: FermaxClient,
        device_id: str,
        door: AccessDoor,
        device_info: FermaxDeviceInfo,
        lock_timeout: int,
    ) -> None:
        self._client = client
        self._device_id = device_id
        self._door = door
        self._model = device_info.model
        self._lock_timeout = lock_timeout
        self._attr_unique_id = f"{device_id}_{door.name}_door_lock".lower()
        self._attr_name = door.title or door.name
        self._attr_is_locked = True
        self._attr_is_locking = False
        self._attr_is_unlocking = False

    async def async_lock(self, **kwargs: Any) -> None:
        pass

    async def async_unlock(self, **kwargs: Any) -> None:
        self._attr_is_unlocking = True
        self.async_write_ha_state()

        await self._client.async_open_door(self._device_id, self._door.access_id)

        self._attr_is_unlocking = False
        self._attr_is_locked = False
        self.async_write_ha_state()

        await asyncio.sleep(self._lock_timeout)
        self._attr_is_locked = True
        self.async_write_ha_state()

    async def async_open(self, **kwargs: Any) -> None:
        await self.async_unlock(**kwargs)

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{self._model} {self._device_id}",
            manufacturer=DEVICE_MANUFACTURER,
            model=self._model,
            sw_version=HASS_BLUECON_VERSION,
        )
