"""Binary sensor for Sesame 4 BLE lock state."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device import Sesame4Device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device: Sesame4Device = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Sesame4LockStateSensor(device, entry)])


class Sesame4LockStateSensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.LOCK

    def __init__(self, device: Sesame4Device, entry: ConfigEntry) -> None:
        self._device = device
        self._entry = entry
        self._attr_unique_id = f"{device.address}_lock_state"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.address)},
            "name": "Sesame 4",
            "manufacturer": "CANDY HOUSE",
            "model": entry.data.get("model", "Sesame 4"),
        }
        self._attr_name = "Lock state"

    @property
    def available(self) -> bool:
        return self._device.is_connected

    @property
    def is_on(self) -> bool | None:
        status = self._device.mech_status
        if status is None:
            return None
        return not status.isLocked()

    @callback
    def _on_device_update(self) -> None:
        self.async_schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._device.add_update_callback(self._on_device_update)

    async def async_will_remove_from_hass(self) -> None:
        self._device.remove_update_callback(self._on_device_update)
        await super().async_will_remove_from_hass()
