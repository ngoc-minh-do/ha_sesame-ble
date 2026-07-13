"""Sesame 4 BLE device - connection, login, lock/unlock operations."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Optional

from cryptography.hazmat.primitives import cmac
from cryptography.hazmat.primitives.ciphers import algorithms

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .const import (
    RX_UUID,
    SERVICE_UUID,
    TX_UUID,
    BleCmdResultCode,
    BleCommunicationType,
    BleItemCode,
    BleOpCode,
)
from .crypto import AppKeyFactory, BleCipher
from .helpers import (
    BleNotify,
    BlePayload,
    BlePublish,
    BleReceiver,
    BleResponse,
    BleTransmitter,
    CHSesame2MechSettings,
    CHSesame2MechStatus,
    create_htag,
)

LOGGER = logging.getLogger(__name__)

STATE_DISCONNECTED = "disconnected"
STATE_CONNECTING = "connecting"
STATE_LOGIN = "login"
STATE_READY = "ready"


class Sesame4Device:
    def __init__(self, address: str, secret_key: str, public_key: str, hass: HomeAssistant) -> None:
        self._address = address
        self._secret_key = bytes.fromhex(secret_key)
        self._sesame_pk: bytes = bytes.fromhex(public_key)
        self._device_id: Optional[str] = None
        self._hass = hass

        self._client = None
        self._cipher: Optional[BleCipher] = None
        self._sesame_token: Optional[bytes] = None
        self._rx_buffer = BleReceiver()
        self._tx_buffer: Optional[BleTransmitter] = None

        self._mech_status: Optional[CHSesame2MechStatus] = None
        self._mech_settings: Optional[CHSesame2MechSettings] = None

        self._state = STATE_DISCONNECTED
        self._callbacks: list[Callable[[], None]] = []
        self._lock = asyncio.Lock()
        self._logged_in = asyncio.Event()

    @property
    def address(self) -> str:
        return self._address

    @property
    def device_id(self) -> Optional[str]:
        return self._device_id

    @property
    def mech_status(self) -> Optional[CHSesame2MechStatus]:
        return self._mech_status

    @property
    def mech_settings(self) -> Optional[CHSesame2MechSettings]:
        return self._mech_settings

    @property
    def is_connected(self) -> bool:
        return self._state == STATE_READY

    def add_update_callback(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def remove_update_callback(self, callback: Callable[[], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_update(self) -> None:
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                LOGGER.exception("Error in update callback")

    async def connect_and_login(self) -> None:
        from bleak import BleakClient
        from homeassistant.components.bluetooth import async_ble_device_from_address

        self._state = STATE_CONNECTING
        LOGGER.debug("Connecting to %s", self._address)

        ble_device = async_ble_device_from_address(
            self._hass, self._address, connectable=True
        )
        self._client = BleakClient(ble_device or self._address)
        self._client.set_disconnected_callback(self._on_disconnect)
        await self._client.connect()

        LOGGER.info("Connected to %s", self._address)
        self._state = STATE_LOGIN

        for service in self._client.services:
            if service.uuid == SERVICE_UUID:
                self._tx_char = service.get_characteristic(TX_UUID)
                rx_char = service.get_characteristic(RX_UUID)
                await self._client.start_notify(rx_char, self._on_notify)
                LOGGER.debug("Subscribed to RX characteristic")
                break
        else:
            raise RuntimeError("Sesame service not found on device")

    def _on_disconnect(self, client) -> None:
        LOGGER.warning("Disconnected from %s", self._address)
        self._state = STATE_DISCONNECTED
        self._logged_in.clear()
        self._notify_update()

    async def _transmit(self) -> None:
        if self._tx_buffer is None:
            return
        chunk = self._tx_buffer.getChunk()
        while chunk is not None:
            await self._client.write_gatt_char(self._tx_char, chunk, response=False)
            chunk = self._tx_buffer.getChunk()

    async def _send_command(
        self, payload: BlePayload, is_cipher: BleCommunicationType
    ) -> None:
        if is_cipher == BleCommunicationType.ciphertext:
            if self._cipher is None:
                raise RuntimeError("Cipher not initialized")
            packet_data = self._cipher.encrypt(payload.toDataWithHeader())
        else:
            packet_data = payload.toDataWithHeader()

        self._tx_buffer = BleTransmitter(is_cipher, packet_data)
        await self._transmit()

    async def login(self, remote_pubkey: Optional[bytes] = None) -> None:
        async with self._lock:
            if self._state == STATE_READY:
                return
            await self._do_login(remote_pubkey)
            await self._logged_in.wait()

    async def _do_login(self, remote_pubkey: Optional[bytes] = None) -> None:
        if remote_pubkey:
            self._sesame_pk = remote_pubkey

        local_keys = AppKeyFactory.get_instance()
        local_pk = local_keys.getPubkey()
        local_token = local_keys.getAppToken()

        if self._sesame_token is None:
            self._state = STATE_CONNECTING
            return

        tokens = local_token + self._sesame_token

        c = cmac.CMAC(algorithms.AES(self._secret_key))
        c.update(b"\x00\x00" + local_pk + tokens)
        cmac_tag_response = c.finalize()[:4]

        c = cmac.CMAC(algorithms.AES(local_keys.ecdh(self._sesame_pk)[:16]))
        c.update(tokens)
        cmac_tag = c.finalize()

        self._cipher = BleCipher(cmac_tag, tokens)
        payload = b"\x00\x00" + local_pk + local_token + cmac_tag_response

        LOGGER.debug("Sending login command")
        await self._send_command(
            BlePayload(BleOpCode.sync, BleItemCode.login, payload),
            BleCommunicationType.plaintext,
        )

    async def _on_notify(self, _: int, data: bytearray) -> None:
        comm_type, rawdata = self._rx_buffer.feed(bytes(data))

        if rawdata is None:
            return

        if comm_type == BleCommunicationType.plaintext:
            notify = BleNotify(rawdata)
        elif comm_type == BleCommunicationType.ciphertext:
            if self._cipher is None:
                return
            notify = BleNotify(self._cipher.decrypt(rawdata))
        else:
            return

        if notify.notifyOpCode == BleOpCode.publish:
            publish = BlePublish(notify.payload)
            await self._handle_publish(publish)
        elif notify.notifyOpCode == BleOpCode.response:
            response = BleResponse(notify.payload)
            await self._handle_response(response)

    async def _handle_publish(self, publish: BlePublish) -> None:
        if publish.cmdItCode == BleItemCode.initial:
            self._sesame_token = publish.payload
            LOGGER.debug("Received sesame token, logging in")
            await self._do_login()
        elif publish.cmdItCode == BleItemCode.mechStatus:
            self._mech_status = CHSesame2MechStatus(rawdata=publish.payload)
            LOGGER.debug("Mech status: locked=%s, battery=%s%%",
                         self._mech_status.isLocked(), self._mech_status.getBatteryPercentage())
            self._notify_update()
        elif publish.cmdItCode == BleItemCode.mechSetting:
            self._mech_settings = CHSesame2MechSettings(rawdata=publish.payload)
            LOGGER.debug("Mech settings updated")
            self._notify_update()

    async def _handle_response(self, response: BleResponse) -> None:
        if (
            response.cmdItCode == BleItemCode.login
            and response.cmdResultCode == BleCmdResultCode.success
        ):
            login_data = response.payload
            mech_settings = CHSesame2MechSettings(rawdata=login_data[8:20])
            mech_status = CHSesame2MechStatus(rawdata=login_data[20:28])

            self._mech_settings = mech_settings
            self._mech_status = mech_status
            self._state = STATE_READY
            self._logged_in.set()

            LOGGER.info("Logged in to %s", self._address)
            self._notify_update()
        elif (
            response.cmdItCode == BleItemCode.login
            and response.cmdResultCode != BleCmdResultCode.success
        ):
            LOGGER.error("Login failed: %s", response.cmdResultCode)
            self._state = STATE_DISCONNECTED
            self._logged_in.clear()
            self._notify_update()

    async def lock(self, tag: str = "HA") -> None:
        if not self.is_connected:
            raise RuntimeError("Device not connected")
        LOGGER.info("Locking %s", self._address)
        await self._send_command(
            BlePayload(BleOpCode.async_, BleItemCode.lock, create_htag(tag)),
            BleCommunicationType.ciphertext,
        )

    async def unlock(self, tag: str = "HA") -> None:
        if not self.is_connected:
            raise RuntimeError("Device not connected")
        LOGGER.info("Unlocking %s", self._address)
        await self._send_command(
            BlePayload(BleOpCode.async_, BleItemCode.unlock, create_htag(tag)),
            BleCommunicationType.ciphertext,
        )

    async def toggle(self, tag: str = "HA") -> None:
        if not self.is_connected:
            raise RuntimeError("Device not connected")
        if self._mech_status is None:
            raise RuntimeError("Status unknown")
        if self._mech_status.isInLockRange():
            await self.unlock(tag)
        else:
            await self.lock(tag)

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(RX_UUID)
            except Exception:
                pass
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._state = STATE_DISCONNECTED
        self._logged_in.clear()
        LOGGER.info("Disconnected from %s", self._address)
