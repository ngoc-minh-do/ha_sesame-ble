"""Coordinator for Sesame BLE — connection lifecycle, concurrency, availability."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL, LOGIN_TIMEOUT
from .device import SesameDevice
from .helpers import CHSesame2MechSettings, CHSesame2MechStatus

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SesameState:
    mech_status: CHSesame2MechStatus | None
    mech_settings: CHSesame2MechSettings | None


class SesameCoordinator(DataUpdateCoordinator[SesameState]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: SesameDevice,
    ) -> None:
        self._device = device
        self._connection_lock = asyncio.Lock()

        super().__init__(
            hass,
            LOGGER,
            name=f"Sesame BLE {device.address}",
            config_entry=entry,
            update_interval=None,
        )

        self._device.add_update_callback(self._on_device_update)

    @property
    def address(self) -> str:
        return self._device.address

    @property
    def _current_state(self) -> SesameState:
        return SesameState(
            mech_status=self._device.mech_status,
            mech_settings=self._device.mech_settings,
        )

    async def _async_update_data(self) -> SesameState:
        try:
            await self._ensure_connected()
        except Exception as err:
            raise UpdateFailed(f"Unable to refresh Sesame: {err}") from err
        return self._current_state

    def _on_device_update(self) -> None:
        self.async_set_updated_data(self._current_state)

    async def _ensure_connected(self) -> None:
        async with self._connection_lock:
            connected = self._device.is_connected
            stale = self._device.session_stale
            LOGGER.debug(
                "ensure_connected: is_connected=%s, stale=%s", connected, stale
            )
            if connected and not stale:
                return
            LOGGER.debug("ensure_connected: connecting fresh")
            await self._device.connect()
            await asyncio.wait_for(self._device.authenticate(), timeout=LOGIN_TIMEOUT)

    async def lock(self, tag: str = "HA") -> None:
        await self._ensure_connected()
        await self._device.lock(tag)

    async def unlock(self, tag: str = "HA") -> None:
        await self._ensure_connected()
        await self._device.unlock(tag)

    def start_periodic_refresh(self) -> None:
        assert self.config_entry is not None
        interval_minutes = self.config_entry.options.get(
            CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL
        )
        if interval_minutes == 0:
            self.update_interval = None
            LOGGER.info("Periodic refresh disabled")
            return

        self.update_interval = timedelta(minutes=interval_minutes)
        LOGGER.info("Periodic refresh every %d minutes", interval_minutes)

    def restart_periodic_refresh(self) -> None:
        LOGGER.debug("Options changed, restarting periodic refresh")
        self.start_periodic_refresh()

    async def shutdown(self) -> None:
        self._device.remove_update_callback(self._on_device_update)
        await self._device.disconnect()
