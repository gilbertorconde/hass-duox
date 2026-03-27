"""Binary sensor platform for Fermax Blue."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_MANUFACTURER,
    DOMAIN,
    HASS_BLUECON_VERSION,
    SIGNAL_CALL_ENDED,
    SIGNAL_CALL_STARTED,
)
from .coordinator import FermaxCoordinator
from .fermax_api import DeviceInfo as FermaxDeviceInfo, Pairing


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FermaxCoordinator = hass.data[DOMAIN][config.entry_id]["coordinator"]
    pairings: list[Pairing] = hass.data[DOMAIN][config.entry_id]["pairings"]
    has_fcm: bool = hass.data[DOMAIN][config.entry_id].get("has_fcm", False)

    sensors: list[BinarySensorEntity] = []

    for pairing in pairings:
        device_info: FermaxDeviceInfo = hass.data[DOMAIN][config.entry_id][
            "device_info"
        ][pairing.device_id]

        sensors.append(
            BlueConConnectionSensor(coordinator, pairing.device_id, device_info)
        )

        if has_fcm:
            for door in pairing.access_doors:
                if not door.visible:
                    continue
                sensors.append(
                    BlueConDoorbellSensor(
                        pairing.device_id, door.name, device_info
                    )
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


class BlueConDoorbellSensor(BinarySensorEntity):
    """Binary sensor that turns on when the doorbell rings (via FCM push)."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_should_poll = False

    def __init__(
        self,
        device_id: str,
        access_door_name: str,
        device_info: FermaxDeviceInfo,
    ) -> None:
        self._device_id = device_id
        self._access_door_name = access_door_name
        self._model = device_info.model
        self._attr_unique_id = (
            f"{device_id}_{access_door_name}_doorbell".lower()
        )
        self._attr_name = f"Doorbell {access_door_name}"
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CALL_STARTED.format(
                    self._device_id, self._access_door_name
                ),
                self._call_started,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CALL_ENDED.format(self._device_id),
                self._call_ended,
            )
        )

    @callback
    def _call_started(self) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    @callback
    def _call_ended(self) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{self._model} {self._device_id}",
            manufacturer=DEVICE_MANUFACTURER,
            model=self._model,
            sw_version=HASS_BLUECON_VERSION,
        )
