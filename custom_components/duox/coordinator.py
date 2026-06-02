"""DataUpdateCoordinator for Fermax Duox."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .fermax_api import DeviceInfo, FermaxClient, FermaxConnectionError, Pairing

LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)

# Tolerate a few transient API failures before marking entities unavailable,
# keeping the last known-good data in the meantime.
MAX_FAILURES_BEFORE_UNAVAILABLE = 3


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
            name="Fermax Duox",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.pairings = pairings
        self._consecutive_failures = 0

    async def _async_update_data(self) -> dict[str, DeviceInfo]:
        # ConfigEntryAuthFailed (raised by the client on unrecoverable auth
        # errors) intentionally propagates so HA can trigger re-authentication.
        try:
            result: dict[str, DeviceInfo] = {}
            for pairing in self.pairings:
                info = await self.client.async_get_device_info(pairing.device_id)
                result[pairing.device_id] = info
            self._consecutive_failures = 0
            return result
        except FermaxConnectionError as err:
            self._consecutive_failures += 1
            if (
                self.data
                and self._consecutive_failures < MAX_FAILURES_BEFORE_UNAVAILABLE
            ):
                LOGGER.warning(
                    "Error communicating with Fermax API (%d/%d), "
                    "using cached data: %s",
                    self._consecutive_failures,
                    MAX_FAILURES_BEFORE_UNAVAILABLE,
                    err,
                )
                return self.data
            raise UpdateFailed(f"Error communicating with Fermax API: {err}") from err
