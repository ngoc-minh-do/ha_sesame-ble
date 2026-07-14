"""Lock entity for Sesame BLE integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_MODEL_NAME, DOMAIN
from .coordinator import SesameCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SesameCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SesameBleLock(coordinator, entry)])


class SesameBleLock(LockEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SesameCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{coordinator.address}_lock"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.address)},
            "name": "Sesame BLE Lock",
            "manufacturer": "CANDY HOUSE",
            "model": entry.data.get("model", DEFAULT_MODEL_NAME),
        }
        self._attr_name = "Lock"

    @property
    def available(self) -> bool:
        return self._coordinator.available

    @property
    def is_locked(self) -> bool | None:
        status = self._coordinator.mech_status
        if status is None:
            return None
        return status.isLocked()

    @property
    def is_locking(self) -> bool:
        status = self._coordinator.mech_status
        if status is None:
            return False
        target = status.getTarget()
        settings = self._coordinator.mech_settings
        if settings is None:
            return False
        return target == settings.getLockPosition() and not status.isInLockRange()

    @property
    def is_unlocking(self) -> bool:
        status = self._coordinator.mech_status
        if status is None:
            return False
        target = status.getTarget()
        settings = self._coordinator.mech_settings
        if settings is None:
            return False
        return target == settings.getUnlockPosition() and not status.isInUnlockRange()

    async def async_lock(self, **kwargs: Any) -> None:
        await self._coordinator.lock()

    async def async_unlock(self, **kwargs: Any) -> None:
        await self._coordinator.unlock()

    @callback
    def _on_coordinator_update(self) -> None:
        self.async_schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.add_update_callback(self._on_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_update_callback(self._on_coordinator_update)
        await super().async_will_remove_from_hass()
