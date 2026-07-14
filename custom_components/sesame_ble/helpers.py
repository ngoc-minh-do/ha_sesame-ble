"""Protocol helpers: mech status, BLE packet framing, product model."""

import base64
import uuid
from typing import Optional, Tuple, Union

from .const import (
    BleCmdResultCode,
    BleCommunicationType,
    BleItemCode,
    BleOpCode,
    BlePacketType,
)


class CHSesame2MechStatus:
    def __init__(self, rawdata: Union[bytes, str]) -> None:
        if isinstance(rawdata, str):
            data = bytes.fromhex(rawdata)
        elif isinstance(rawdata, bytes):
            data = rawdata
        else:
            raise TypeError("Invalid mech status data")

        self._data = data
        self._batteryVoltage = int.from_bytes(data[0:2], "little") * 7.2 / 1023
        _raw_target = int.from_bytes(data[2:4], "little", signed=True)
        self._target: Optional[int] = None if _raw_target == -32768 else int(_raw_target * 360 / 1024)
        self._position = int(int.from_bytes(data[4:6], "little", signed=True) * 360 / 1024)
        self._retcode = data[6]
        self._isInLockRange = (data[7] & 2) != 0
        self._isInUnlockRange = (data[7] & 4) != 0
        self._isBatteryCritical = (data[7] & 32) != 0

    def getBatteryVoltage(self) -> float:
        return self._batteryVoltage

    def getBatteryPercentage(self) -> int:
        list_vol = [6.0, 5.8, 5.7, 5.6, 5.4, 5.2, 5.1, 5.0, 4.8, 4.6]
        list_pct = [100.0, 50.0, 40.0, 32.0, 21.0, 13.0, 10.0, 7.0, 3.0, 0.0]
        cur_vol = self._batteryVoltage

        if cur_vol >= list_vol[0]:
            return 100
        elif cur_vol <= list_vol[-1]:
            return 0

        for i in range(len(list_vol) - 1):
            if list_vol[i] > cur_vol >= list_vol[i + 1]:
                f = (cur_vol - list_vol[i + 1]) / (list_vol[i] - list_vol[i + 1])
                return int(list_pct[i + 1] + f * (list_pct[i] - list_pct[i + 1]))

        return 0

    def getTarget(self) -> Optional[int]:
        return self._target

    def getPosition(self) -> int:
        return self._position

    def getRetCode(self) -> int:
        return self._retcode

    def isInLockRange(self) -> bool:
        return self._isInLockRange

    def isInUnlockRange(self) -> bool:
        return self._isInUnlockRange

    def isBatteryCritical(self) -> bool:
        return self._isBatteryCritical

    def isLocked(self) -> Optional[bool]:
        if self._isInLockRange:
            return True
        if self._isInUnlockRange:
            return False
        return None


class CHSesame2MechSettings:
    def __init__(self, rawdata: Union[bytes, str]) -> None:
        if isinstance(rawdata, str):
            data = bytes.fromhex(rawdata)
        elif isinstance(rawdata, bytes):
            data = rawdata
        else:
            raise TypeError("Invalid mech settings data")

        self._lockPosition = int(int.from_bytes(data[0:2], "little", signed=True) * 360 / 1024)
        self._unlockPosition = int(int.from_bytes(data[2:4], "little", signed=True) * 360 / 1024)

    @property
    def isConfigured(self) -> bool:
        return self._lockPosition != self._unlockPosition

    def getLockPosition(self) -> int:
        return self._lockPosition

    def getUnlockPosition(self) -> int:
        return self._unlockPosition


class CHProductModel:
    _models = {
        0: {"deviceModel": "sesame_2", "isLocker": True},
        1: {"deviceModel": "wm_2", "isLocker": False},
        2: {"deviceModel": "ssmbot_1", "isLocker": True},
        4: {"deviceModel": "sesame_4", "isLocker": True},
    }

    _name_map = {
        0: "Sesame 3",
        1: "Wifi Module 2",
        2: "Sesame Bot 1",
        4: "Sesame 4",
    }

    def __init__(self, product_type: int) -> None:
        if product_type not in self._models:
            raise NotImplementedError(f"Unknown product type: {product_type}")
        self._product_type = product_type

    @classmethod
    def getByValue(cls, val: int) -> "CHProductModel":
        return cls(val)

    @property
    def productType(self) -> int:
        return self._product_type

    @property
    def deviceModel(self) -> str:
        return self._models[self._product_type]["deviceModel"]

    @property
    def isLocker(self) -> bool:
        return self._models[self._product_type]["isLocker"]

    @property
    def displayName(self) -> str:
        return self._name_map.get(self._product_type, f"Sesame (type {self._product_type})")


class BLEAdvertisement:
    def __init__(self, dev, manufacturer_data: dict, rssi: int = -100) -> None:
        self._address = dev.address
        self._device = dev
        self._rssi = rssi
        self._advBytes = next(iter(manufacturer_data.values()))
        self._product_type = self._advBytes[0]
        self._isRegistered = (self._advBytes[2] & 1) > 0

        if self._product_type == 1:
            self._deviceId = uuid.UUID(
                "00000000055afd810001" + self._advBytes[3:9].hex()
            )
        else:
            try:
                self._deviceId = uuid.UUID(
                    bytes=base64.b64decode(dev.name + "==")
                )
            except Exception:
                self._deviceId = None

    @property
    def address(self) -> str:
        return self._address

    @property
    def device(self):
        return self._device

    @property
    def rssi(self) -> int:
        return self._rssi

    @property
    def deviceId(self) -> Optional[uuid.UUID]:
        return self._deviceId

    @property
    def productType(self) -> int:
        return self._product_type

    @property
    def isRegistered(self) -> bool:
        return self._isRegistered


def create_htag(tag: str) -> bytes:
    body = tag.encode("utf-8")[:21]
    header = bytes([len(body)])
    padding = b"\x00" * (22 - len(header + body))
    return header + body + padding


class BleTransmitter:
    MTU = 19

    def __init__(self, segment_type: BleCommunicationType, data: bytes) -> None:
        self._segment_type = segment_type
        self._chunks = [
            data[i : i + self.MTU] for i in range(0, len(data), self.MTU)
        ]
        self._is_first = True

    def getChunk(self) -> Optional[bytes]:
        if not self._chunks:
            return None

        chunk = self._chunks.pop(0)
        remaining = len(self._chunks)

        if self._is_first:
            packet_type = BlePacketType.isStart
            self._is_first = False
        else:
            packet_type = BlePacketType.NotStart

        comm_bits = self._segment_type.value if remaining == 0 else BlePacketType.APPEND_ONLY.value

        header = bytes([packet_type.value | (comm_bits << 1)])
        return header + chunk


class BleReceiver:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> Tuple[Optional[BleCommunicationType], Optional[bytes]]:
        header = data[0]
        is_start = header & 1
        comm_type = header >> 1

        if is_start:
            self._buffer = bytearray(data[1:])
        else:
            self._buffer += data[1:]

        if comm_type == 0:
            return None, None

        return BleCommunicationType(comm_type), bytes(self._buffer)


class BlePayload:
    def __init__(self, op_code: BleOpCode, item_code: BleItemCode, data: bytes) -> None:
        self._op_code = op_code
        self._item_code = item_code
        self._data = data

    @property
    def opCode(self) -> BleOpCode:
        return self._op_code

    @property
    def itCode(self) -> BleItemCode:
        return self._item_code

    def toDataWithHeader(self) -> bytes:
        return bytes([self._op_code.value, self._item_code.value]) + self._data


class BleNotify:
    def __init__(self, data: bytes) -> None:
        self._notifyOpCode = BleOpCode(int(data[0]))
        self._payload = data[1:]

    @property
    def notifyOpCode(self) -> BleOpCode:
        return self._notifyOpCode

    @property
    def payload(self) -> bytes:
        return self._payload


class BlePublish:
    def __init__(self, data: bytes) -> None:
        self._cmdItCode = BleItemCode(int(data[0]))
        self._payload = data[1:]

    @property
    def cmdItCode(self) -> BleItemCode:
        return self._cmdItCode

    @property
    def payload(self) -> bytes:
        return self._payload


class BleResponse:
    def __init__(self, data: bytes) -> None:
        self._cmdItCode = BleItemCode(int(data[0]))
        self._cmdOPCode = BleOpCode(int(data[1]))
        self._cmdResultCode = BleCmdResultCode(int(data[2]))
        self._payload = data[3:]

    @property
    def cmdItCode(self) -> BleItemCode:
        return self._cmdItCode

    @property
    def cmdOPCode(self) -> BleOpCode:
        return self._cmdOPCode

    @property
    def cmdResultCode(self) -> BleCmdResultCode:
        return self._cmdResultCode

    @property
    def payload(self) -> bytes:
        return self._payload


def decode_sk(sk_base64: str) -> tuple[str, str]:
    data = base64.b64decode(sk_base64)
    if len(data) < 81:
        raise ValueError(
            f"SK data too short: {len(data)} bytes, expected at least 81"
        )
    secret = data[1:17].hex()
    pubkey = data[17:81].hex()
    return secret, pubkey
