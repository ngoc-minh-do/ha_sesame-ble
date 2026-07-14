"""The Sesame BLE integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_PUBLIC_KEY, CONF_SECRET_KEY, DOMAIN
from .coordinator import SesameCoordinator
from .device import SesameDevice

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    device = SesameDevice(
        address=entry.data[CONF_ADDRESS],
        secret_key=entry.data[CONF_SECRET_KEY],
        public_key=entry.data[CONF_PUBLIC_KEY],
        hass=hass,
    )

    coordinator = SesameCoordinator(hass, entry, device)

    try:
        await coordinator.initial_connect()
    except Exception as err:
        LOGGER.exception("Failed to connect to Sesame BLE")
        await coordinator.shutdown()
        raise ConfigEntryNotReady from err

    coordinator.start_periodic_refresh()

    async def _update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
        coordinator.restart_periodic_refresh()

    entry.async_on_unload(entry.add_update_listener(_update_options))

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: SesameCoordinator | None = hass.data[DOMAIN].pop(
            entry.entry_id, None
        )
        if coordinator:
            await coordinator.shutdown()

    return unload_ok
