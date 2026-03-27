"""Camera platform for Fermax Duox — shows the last doorbell snapshot."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.camera import Camera
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
)
from .fermax_api import DeviceInfo as FermaxDeviceInfo, FermaxClient, Pairing

LOGGER = logging.getLogger(__name__)

SNAPSHOT_CACHE_TTL = 120  # seconds


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][config.entry_id]
    client: FermaxClient = data["client"]
    pairings: list[Pairing] = data["pairings"]

    cameras: list[DuoxCamera] = []
    for pairing in pairings:
        device_info: FermaxDeviceInfo = data["device_info"][pairing.device_id]
        if not device_info.photocaller:
            continue
        cameras.append(
            DuoxCamera(
                hass,
                config.entry_id,
                client,
                pairing,
                device_info,
            )
        )

    async_add_entities(cameras)


class DuoxCamera(Camera):
    """Camera entity that displays the last captured doorbell photo."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        client: FermaxClient,
        pairing: Pairing,
        device_info: FermaxDeviceInfo,
    ) -> None:
        super().__init__()
        self._hass = hass
        self._entry_id = entry_id
        self._client = client
        self._device_id = pairing.device_id
        self._model = device_info.model
        self._attr_unique_id = f"{pairing.device_id}_camera".lower()
        self._attr_name = "Duox Doorbell Camera"
        self._cached_image: bytes | None = None
        self._cache_ts: float = 0
        self._fetch_lock = asyncio.Lock()

    async def async_added_to_hass(self) -> None:
        for door in self._get_doors():
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_CALL_STARTED.format(self._device_id, door.name),
                    self._on_doorbell_ring,
                )
            )

    def _get_doors(self) -> list[Any]:
        data = self._hass.data[DOMAIN][self._entry_id]
        for pairing in data["pairings"]:
            if pairing.device_id == self._device_id:
                return [d for d in pairing.access_doors if d.visible]
        return []

    @callback
    def _on_doorbell_ring(self) -> None:
        self._cached_image = None
        self._cache_ts = 0
        self.async_write_ha_state()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        now = time.monotonic()
        if self._cached_image and (now - self._cache_ts) < SNAPSHOT_CACHE_TTL:
            return self._cached_image

        async with self._fetch_lock:
            if self._cached_image and (time.monotonic() - self._cache_ts) < SNAPSHOT_CACHE_TTL:
                return self._cached_image
            image = await self._fetch_latest_photo()
            if image:
                self._cached_image = image
                self._cache_ts = time.monotonic()
            return self._cached_image

    async def _fetch_latest_photo(self) -> bytes | None:
        gcm_token = self._hass.data[DOMAIN][self._entry_id].get("gcm_token")
        if not gcm_token:
            LOGGER.debug("No GCM token available for call registry query")
            return None

        try:
            registry = await self._client.async_get_call_registry(gcm_token)
        except Exception:
            LOGGER.debug("Failed to fetch call registry", exc_info=True)
            return None

        if not registry:
            return None

        photo_id = None
        for entry in registry:
            pid = entry.get("photoId")
            if pid:
                photo_id = pid
                break

        if not photo_id:
            return None

        try:
            return await self._client.async_get_photo(photo_id)
        except Exception:
            LOGGER.debug("Failed to fetch photo %s", photo_id, exc_info=True)
            return None

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{self._model} {self._device_id}",
            manufacturer=DEVICE_MANUFACTURER,
            model=self._model,
            sw_version=HASS_DUOX_VERSION,
        )
