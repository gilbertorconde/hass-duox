"""Button platform for Fermax Duox (F1 relay)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_MANUFACTURER, DOMAIN, HASS_DUOX_VERSION
from .fermax_api import DeviceInfo as FermaxDeviceInfo, FermaxClient, Pairing


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: FermaxClient = hass.data[DOMAIN][config.entry_id]["client"]
    pairings: list[Pairing] = hass.data[DOMAIN][config.entry_id]["pairings"]

    buttons: list[DuoxF1Button] = []
    for pairing in pairings:
        device_info: FermaxDeviceInfo = hass.data[DOMAIN][config.entry_id][
            "device_info"
        ][pairing.device_id]
        buttons.append(DuoxF1Button(client, pairing.device_id, device_info))

    async_add_entities(buttons)


class DuoxF1Button(ButtonEntity):
    _attr_icon = "mdi:keyboard-f1"

    def __init__(
        self,
        client: FermaxClient,
        device_id: str,
        device_info: FermaxDeviceInfo,
    ) -> None:
        self._client = client
        self._device_id = device_id
        self._model = device_info.model
        self._attr_unique_id = f"{device_id}_f1_button".lower()
        self._attr_name = "Duox F1"

    async def async_press(self) -> None:
        await self._client.async_f1(self._device_id)

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{self._model} {self._device_id}",
            manufacturer=DEVICE_MANUFACTURER,
            model=self._model,
            sw_version=HASS_DUOX_VERSION,
        )
