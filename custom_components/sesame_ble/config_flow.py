"""Config flow for Sesame BLE integration."""

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

from .const import (
    CONF_DEVICE_ID,
    CONF_MODEL,
    CONF_PUBLIC_KEY,
    CONF_REFRESH_INTERVAL,
    CONF_SECRET_KEY,
    DEFAULT_REFRESH_INTERVAL,
    LOGIN_TIMEOUT,
    DOMAIN,
    SERVICE_UUID,
)
from .device import SesameDevice
from .helpers import CHProductModel, BLEAdvertisement, decode_sk

LOGGER = logging.getLogger(__name__)


def _parse_discovery(
    discovery_info: BluetoothServiceInfoBleak,
) -> dict[str, Any] | None:
    name = discovery_info.device.name or "(no name)"

    if SERVICE_UUID not in discovery_info.advertisement.service_uuids:
        LOGGER.debug("BLE scan: skipping %s - service UUID not present", name)
        return None

    manufacturer_data = discovery_info.advertisement.manufacturer_data
    if not manufacturer_data:
        LOGGER.debug("BLE scan: skipping %s - no manufacturer data", name)
        return None

    try:
        adv = BLEAdvertisement(
            discovery_info.device,
            manufacturer_data,
            discovery_info.rssi,
        )
    except Exception as exc:
        LOGGER.warning(
            "BLE scan: failed to parse BLE advertisement for %s: %s",
            name,
            exc,
        )
        return None

    if not adv.isRegistered:
        LOGGER.debug("BLE scan: skipping %s - not registered", name)
        return None

    try:
        model = CHProductModel.getByValue(adv.productType)
    except NotImplementedError:
        LOGGER.debug(
            "BLE scan: skipping %s - unsupported productType %s",
            name,
            adv.productType,
        )
        return None

    LOGGER.debug("BLE scan: found %s - %s", name, model.displayName)
    return {
        CONF_ADDRESS: adv.address,
        CONF_DEVICE_ID: str(adv.deviceId) if adv.deviceId else adv.address,
        CONF_MODEL: model.displayName,
        "name": f"{model.displayName} ({adv.address})",
        "rssi": adv.rssi,
    }


def _scan_sesame_devices(hass) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    all_ble = list(async_discovered_service_info(hass))
    LOGGER.debug("BLE scan: %d total devices known to HA", len(all_ble))

    for discovery_info in all_ble:
        result = _parse_discovery(discovery_info)
        if result is not None:
            devices.append(result)

    devices.sort(key=lambda d: d["rssi"], reverse=True)

    LOGGER.info("BLE scan: %d Sesame device(s) found", len(devices))
    return devices


class SesameBleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
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

        options = [{"value": d[CONF_ADDRESS], "label": d["name"]} for d in devices]

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
            sk_value = user_input[CONF_SECRET_KEY].strip()

            try:
                secret_hex, pubkey_hex = decode_sk(sk_value)
            except Exception:
                errors[CONF_SECRET_KEY] = "invalid_sk"
            else:
                if not errors:
                    device_info = self._selected_device or {}
                    errors = await self._test_connection(
                        device_info.get(CONF_ADDRESS, ""),
                        secret_hex,
                        pubkey_hex,
                    )

            if not errors and self._selected_device is not None:
                return self.async_create_entry(
                    title=self._selected_device.get("name", "Sesame BLE"),
                    data={
                        CONF_ADDRESS: self._selected_device[CONF_ADDRESS],
                        CONF_DEVICE_ID: self._selected_device[CONF_DEVICE_ID],
                        CONF_SECRET_KEY: secret_hex,
                        CONF_PUBLIC_KEY: pubkey_hex,
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
        self, address: str, secret_key: str, public_key: str
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        device = SesameDevice(address, secret_key, public_key, self.hass)

        try:
            await device.connect()
            await asyncio.wait_for(device.authenticate(), timeout=LOGIN_TIMEOUT)
        except asyncio.TimeoutError:
            errors["base"] = "timeout"
        except Exception:
            LOGGER.exception("Connection test failed for %s", address)
            errors["base"] = "cannot_connect"
        finally:
            await device.disconnect()

        return errors

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._selected_device = _parse_discovery(discovery_info)
        if self._selected_device is None:
            return self.async_abort(reason="not_supported")

        self.context["title_placeholders"] = {"name": self._selected_device["name"]}
        return await self.async_step_secret()

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return SesameBleOptionsFlow(config_entry)


class SesameBleOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(
                data={CONF_REFRESH_INTERVAL: int(user_input[CONF_REFRESH_INTERVAL])}
            )

        current = self._config_entry.options.get(
            CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL
        )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_REFRESH_INTERVAL,
                    default=str(current),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "0", "label": "Disabled"},
                            {"value": "5", "label": "5 min"},
                            {"value": "10", "label": "10 min"},
                            {"value": "30", "label": "30 min"},
                            {"value": "60", "label": "60 min"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
        )
