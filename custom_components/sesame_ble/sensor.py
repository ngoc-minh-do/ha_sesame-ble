"""Sensor entities for Sesame BLE integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SesameConfigEntry
from .coordinator import SesameCoordinator
from .helpers import get_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SesameConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([SesameBleBatterySensor(coordinator, entry)])


class SesameBleBatterySensor(CoordinatorEntity[SesameCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: SesameCoordinator, entry: SesameConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_battery"
        self._attr_device_info = get_device_info(coordinator, entry)

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None or data.mech_status is None:
            return None
        return data.mech_status.getBatteryPercentage()
