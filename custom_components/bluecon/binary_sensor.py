"""Binary sensor platform for Fermax Blue (connection status)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_MANUFACTURER, DOMAIN, HASS_BLUECON_VERSION
from .coordinator import FermaxCoordinator
from .fermax_api import DeviceInfo as FermaxDeviceInfo, Pairing


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FermaxCoordinator = hass.data[DOMAIN][config.entry_id]["coordinator"]
    pairings: list[Pairing] = hass.data[DOMAIN][config.entry_id]["pairings"]

    sensors: list[BlueConConnectionSensor] = []
    for pairing in pairings:
        device_info: FermaxDeviceInfo = hass.data[DOMAIN][config.entry_id][
            "device_info"
        ][pairing.device_id]
        sensors.append(
            BlueConConnectionSensor(coordinator, pairing.device_id, device_info)
        )

    async_add_entities(sensors)


class BlueConConnectionSensor(
    CoordinatorEntity[FermaxCoordinator], BinarySensorEntity
):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: FermaxCoordinator,
        device_id: str,
        device_info: FermaxDeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._model = device_info.model
        self._attr_unique_id = f"{device_id}_connection_status".lower()
        self._attr_name = "Connection"

    @property
    def is_on(self) -> bool | None:
        info = self.coordinator.data.get(self._device_id)
        if info is None:
            return None
        return info.is_connected

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{self._model} {self._device_id}",
            manufacturer=DEVICE_MANUFACTURER,
            model=self._model,
            sw_version=HASS_BLUECON_VERSION,
        )
