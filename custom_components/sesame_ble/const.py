"""Constants for the Sesame BLE integration."""

from enum import Enum, auto

DOMAIN = "sesame_ble"

CONF_ADDRESS = "address"
CONF_DEVICE_ID = "device_id"
CONF_SECRET_KEY = "secret_key"
CONF_PUBLIC_KEY = "public_key"
CONF_REFRESH_INTERVAL = "refresh_interval"
CONF_MODEL = "model"

DEFAULT_REFRESH_INTERVAL = 0

DEFAULT_MODEL_NAME = "Sesame BLE"

SERVICE_UUID = "0000fd81-0000-1000-8000-00805f9b34fb"
TX_UUID = "16860002-a5ae-9856-b6d3-dbb4c676993e"
RX_UUID = "16860003-a5ae-9856-b6d3-dbb4c676993e"


class CHDeviceLoginStatus(Enum):
    Login = auto()
    UnLogin = auto()


class BleItemCode(Enum):
    none = 0
    registration = 1
    login = 2
    user = 3
    history = 4
    versionTag = 5
    disconnectRebootNow = 6
    enableDFU = 7
    time = 8
    bleConnectionParam = 9
    bleAdvParam = 10
    autolock = 11
    serverAdvKick = 12
    ssmtoken = 13
    initial = 14
    IRER = 15
    timePhone = 16
    mechSetting = 80
    mechStatus = 81
    lock = 82
    unlock = 83
    moveTo = 84
    driveDirection = 85
    stop = 86
    detectDir = 87
    toggle = 88
    click = 89


class BleOpCode(Enum):
    create = 1
    read = 2
    update = 3
    delete = 4
    sync = 5
    async_ = 6
    response = 7
    publish = 8
    undefine = 16


class BleCommunicationType(Enum):
    plaintext = 1
    ciphertext = 2


class BlePacketType(Enum):
    APPEND_ONLY = 0
    isStart = 1
    NotStart = 0


class BleCmdResultCode(Enum):
    success = 0
    invalidFormat = 1
    notSupported = 2
    StorageFail = 3
    invalidSig = 4
    notFound = 5
    UNKNOWN = 6
    BUSY = 7
    INVALID_PARAM = 8
