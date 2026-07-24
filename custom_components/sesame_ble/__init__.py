"""The Sesame BLE integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_PUBLIC_KEY, CONF_SECRET_KEY
from .coordinator import SesameCoordinator
from .device import SesameDevice

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.SENSOR,
]

type SesameConfigEntry = ConfigEntry[SesameCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SesameConfigEntry) -> bool:
    device = SesameDevice(
        address=entry.data[CONF_ADDRESS],
        secret_key=entry.data[CONF_SECRET_KEY],
        public_key=entry.data[CONF_PUBLIC_KEY],
        hass=hass,
    )

    coordinator = SesameCoordinator(hass, entry, device)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        LOGGER.exception("Failed to connect to Sesame BLE")
        await coordinator.shutdown()
        raise ConfigEntryNotReady from err

    coordinator.start_periodic_refresh()

    async def _update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
        coordinator.restart_periodic_refresh()

    entry.async_on_unload(entry.add_update_listener(_update_options))

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SesameConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        await entry.runtime_data.shutdown()

    return unload_ok
