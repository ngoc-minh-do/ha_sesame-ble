"""Config flow for Sesame 4 BLE integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_DEVICE_ID, CONF_MODEL, CONF_SECRET_KEY, DOMAIN, SERVICE_UUID
from .device import Sesame4Device
from .helpers import CHProductModel, BLEAdvertisement

LOGGER = logging.getLogger(__name__)


def _scan_sesame_devices(hass) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []

    for discovery_info in async_discovered_service_info(hass):
        if SERVICE_UUID not in discovery_info.advertisement.service_uuids:
            continue

        manufacturer_data = discovery_info.advertisement.manufacturer_data
        if not manufacturer_data:
            continue

        try:
            adv = BLEAdvertisement(
                discovery_info.device,
                manufacturer_data,
            )
        except Exception:
            continue

        if not adv.isRegistered:
            continue

        try:
            model = CHProductModel.getByValue(adv.productType)
        except NotImplementedError:
            continue

        devices.append(
            {
                CONF_ADDRESS: adv.address,
                CONF_DEVICE_ID: str(adv.deviceId) if adv.deviceId else adv.address,
                CONF_MODEL: model.displayName,
                "name": f"{model.displayName} ({adv.address})",
                "rssi": adv.rssi,
            }
        )

    return devices


class Sesame4ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_devices: dict[str, dict[str, Any]] = {}
        self._selected_device: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_addr = user_input[CONF_ADDRESS]
            self._selected_device = self._discovered_devices[selected_addr]
            await self.async_set_unique_id(selected_addr)
            self._abort_if_unique_id_configured()
            return await self.async_step_secret()

        devices = _scan_sesame_devices(self.hass)

        if not devices:
            return self.async_abort(reason="no_devices_found")

        self._discovered_devices = {d[CONF_ADDRESS]: d for d in devices}

        options = [
            {"value": d[CONF_ADDRESS], "label": d["name"]}
            for d in devices
        ]

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_secret(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            secret_key = user_input[CONF_SECRET_KEY].strip().replace(" ", "")

            if len(secret_key) != 32:
                errors[CONF_SECRET_KEY] = "invalid_key_length"
            else:
                try:
                    bytes.fromhex(secret_key)
                except ValueError:
                    errors[CONF_SECRET_KEY] = "invalid_hex"
                else:
                    if not errors:
                        device_info = self._selected_device or {}
                        errors = await self._test_connection(
                            device_info.get(CONF_ADDRESS, ""), secret_key
                        )

            if not errors and self._selected_device is not None:
                return self.async_create_entry(
                    title=self._selected_device.get("name", "Sesame 4"),
                    data={
                        CONF_ADDRESS: self._selected_device[CONF_ADDRESS],
                        CONF_DEVICE_ID: self._selected_device[CONF_DEVICE_ID],
                        CONF_SECRET_KEY: secret_key,
                        CONF_MODEL: self._selected_device[CONF_MODEL],
                    },
                )

        device_name = (
            self._selected_device.get("name", "Unknown")
            if self._selected_device
            else "Unknown"
        )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_SECRET_KEY): str,
            }
        )

        return self.async_show_form(
            step_id="secret",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"device": device_name},
        )

    async def _test_connection(
        self, address: str, secret_key: str
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        device = Sesame4Device(address, secret_key, self.hass)

        try:
            await device.connect_and_login()
            await asyncio.wait_for(device.login(), timeout=15.0)
        except asyncio.TimeoutError:
            errors["base"] = "timeout"
        except Exception:
            LOGGER.exception("Connection test failed")
            errors["base"] = "cannot_connect"
        finally:
            await device.disconnect()

        return errors

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        manufacturer_data = discovery_info.advertisement.manufacturer_data
        if not manufacturer_data:
            return self.async_abort(reason="not_supported")

        try:
            adv = BLEAdvertisement(
                discovery_info.device,
                manufacturer_data,
            )
        except Exception:
            return self.async_abort(reason="not_supported")

        if not adv.isRegistered:
            return self.async_abort(reason="not_registered")

        try:
            model = CHProductModel.getByValue(adv.productType)
        except NotImplementedError:
            return self.async_abort(reason="not_supported")

        self._selected_device = {
            CONF_ADDRESS: adv.address,
            CONF_DEVICE_ID: str(adv.deviceId) if adv.deviceId else adv.address,
            CONF_MODEL: model.displayName,
            "name": f"{model.displayName} ({adv.address})",
        }

        self.context["title_placeholders"] = {"name": self._selected_device["name"]}
        return await self.async_step_secret()
