"""The Sesame 4 BLE integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_SECRET_KEY, DOMAIN
from .device import Sesame4Device

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    device = Sesame4Device(
        address=entry.data[CONF_ADDRESS],
        secret_key=entry.data[CONF_SECRET_KEY],
        hass=hass,
    )

    try:
        await device.connect_and_login()
        await asyncio.wait_for(device.login(), timeout=15.0)
    except Exception as err:
        LOGGER.exception("Failed to connect to Sesame 4")
        await device.disconnect()
        raise ConfigEntryNotReady from err

    hass.data[DOMAIN][entry.entry_id] = device

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        device: Sesame4Device | None = hass.data[DOMAIN].pop(entry.entry_id, None)
        if device:
            await device.disconnect()

    return unload_ok
