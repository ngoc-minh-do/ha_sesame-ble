"""Coordinator for Sesame 4 BLE — connection lifecycle, concurrency, availability."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Callable, Optional

from .const import CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL
from .device import Sesame4Device
from .helpers import CHSesame2MechSettings, CHSesame2MechStatus

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.event import EventSubscription

LOGGER = logging.getLogger(__name__)

FAILURE_THRESHOLD = 3


class Sesame4Coordinator:
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: Sesame4Device,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._device = device

        self._connection_lock = asyncio.Lock()
        self._failure_count = 0
        self._available = True

        self._callbacks: list[Callable[[], None]] = []
        self._refresh_cancel: Optional[EventSubscription] = None

        self._device.add_update_callback(self._on_device_update)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def mech_status(self) -> Optional[CHSesame2MechStatus]:
        return self._device.mech_status

    @property
    def mech_settings(self) -> Optional[CHSesame2MechSettings]:
        return self._device.mech_settings

    @property
    def address(self) -> str:
        return self._device.address

    def add_update_callback(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def remove_update_callback(self, callback: Callable[[], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _on_device_update(self) -> None:
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                LOGGER.exception("Error in coordinator callback")

    def _set_unavailable(self) -> None:
        if self._available:
            self._available = False
            self._on_device_update()

    def _set_available(self) -> None:
        if not self._available:
            self._available = True
            self._on_device_update()

    async def _ensure_connected(self) -> None:
        async with self._connection_lock:
            connected = self._device._client.is_connected if self._device._client else False
            stale = self._device._session_stale
            LOGGER.debug("ensure_connected: is_connected=%s, stale=%s", connected, stale)
            if connected and not stale:
                return
            LOGGER.debug("ensure_connected: connecting fresh")
            try:
                await self._device.connect_and_login()
                await asyncio.wait_for(self._device.login(), timeout=15.0)
                self._failure_count = 0
                self._set_available()
            except Exception:
                self._failure_count += 1
                LOGGER.warning(
                    "Connection failed (%d/%d)", self._failure_count, FAILURE_THRESHOLD
                )
                if self._failure_count >= FAILURE_THRESHOLD:
                    self._set_unavailable()
                raise

    async def initial_connect(self) -> None:
        try:
            await self._device.connect_and_login()
            await asyncio.wait_for(self._device.login(), timeout=15.0)
        except Exception as exc:
            raise exc
        finally:
            await self._device.disconnect()

    async def lock(self, tag: str = "HA") -> None:
        try:
            await self._ensure_connected()
            await self._device.lock(tag)
        finally:
            pass

    async def unlock(self, tag: str = "HA") -> None:
        try:
            await self._ensure_connected()
            await self._device.unlock(tag)
        finally:
            pass

    async def refresh_status(self) -> None:
        if self._connection_lock.locked():
            LOGGER.debug("refresh_status: skipped (lock held)")
            return
        try:
            LOGGER.debug("refresh_status: connecting")
            await self._ensure_connected()
        except Exception:
            LOGGER.debug("refresh_status: failed")
            return
        finally:
            await self._device.disconnect()

    def start_periodic_refresh(self) -> None:
        from homeassistant.helpers.event import async_track_time_interval

        interval_minutes = self._entry.options.get(
            CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL
        )
        if interval_minutes == 0:
            LOGGER.info("Periodic refresh disabled")
            return

        interval = timedelta(minutes=interval_minutes)

        async def _refresh(now=None) -> None:
            await self.refresh_status()

        self._refresh_cancel = async_track_time_interval(
            self._hass, _refresh, interval
        )
        LOGGER.info("Periodic refresh every %d minutes", interval_minutes)

    def restart_periodic_refresh(self) -> None:
        LOGGER.info("Options changed, restarting periodic refresh")
        if self._refresh_cancel is not None:
            self._refresh_cancel()
            self._refresh_cancel = None
        self.start_periodic_refresh()

    async def shutdown(self) -> None:
        if self._refresh_cancel is not None:
            self._refresh_cancel()
            self._refresh_cancel = None
        await self._device.disconnect()
