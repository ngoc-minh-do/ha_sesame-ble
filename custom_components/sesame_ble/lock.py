"""Lock entity for Sesame BLE integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SesameCoordinator
from .helpers import get_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SesameCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SesameBleLock(coordinator, entry)])


class SesameBleLock(CoordinatorEntity[SesameCoordinator], LockEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SesameCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_lock"
        self._attr_device_info = get_device_info(coordinator, entry)
        self._attr_name = "Lock"

    @property
    def is_locked(self) -> bool | None:
        data = self.coordinator.data
        if data is None or data.mech_status is None:
            return None
        return data.mech_status.isLocked()

    @property
    def is_locking(self) -> bool:
        data = self.coordinator.data
        if data is None or data.mech_status is None:
            return False
        target = data.mech_status.getTarget()
        if data.mech_settings is None:
            return False
        return target == data.mech_settings.getLockPosition() and not data.mech_status.isInLockRange()

    @property
    def is_unlocking(self) -> bool:
        data = self.coordinator.data
        if data is None or data.mech_status is None:
            return False
        target = data.mech_status.getTarget()
        if data.mech_settings is None:
            return False
        return target == data.mech_settings.getUnlockPosition() and not data.mech_status.isInUnlockRange()

    async def async_lock(self, **kwargs: Any) -> None:
        await self.coordinator.lock()

    async def async_unlock(self, **kwargs: Any) -> None:
        await self.coordinator.unlock()
