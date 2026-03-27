"""DataUpdateCoordinator for Fermax Blue."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .fermax_api import DeviceInfo, FermaxClient, FermaxConnectionError, Pairing

LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


class FermaxCoordinator(DataUpdateCoordinator[dict[str, DeviceInfo]]):
    """Polls device info for all paired Fermax devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: FermaxClient,
        pairings: list[Pairing],
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name="Fermax Blue",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.pairings = pairings

    async def _async_update_data(self) -> dict[str, DeviceInfo]:
        try:
            result: dict[str, DeviceInfo] = {}
            for pairing in self.pairings:
                info = await self.client.async_get_device_info(pairing.device_id)
                result[pairing.device_id] = info
            return result
        except FermaxConnectionError as err:
            raise UpdateFailed(f"Error communicating with Fermax API: {err}") from err
