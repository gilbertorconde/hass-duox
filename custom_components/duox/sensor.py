"""Sensor platform for Fermax Duox (WiFi signal strength)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_MANUFACTURER, DOMAIN, HASS_DUOX_VERSION
from .coordinator import FermaxCoordinator
from .fermax_api import DeviceInfo as FermaxDeviceInfo, Pairing

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
    coordinator: FermaxCoordinator = hass.data[DOMAIN][config.entry_id]["coordinator"]
    pairings: list[Pairing] = hass.data[DOMAIN][config.entry_id]["pairings"]

    sensors: list[DuoxWifiSensor] = []
    for pairing in pairings:
        device_info: FermaxDeviceInfo = hass.data[DOMAIN][config.entry_id][
            "device_info"
        ][pairing.device_id]
        sensors.append(
            DuoxWifiSensor(coordinator, pairing.device_id, device_info)
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
