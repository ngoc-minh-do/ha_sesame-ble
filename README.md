# Sesame BLE

Home Assistant custom integration for [CANDY HOUSE](https://jp.candyhouse.co/) Sesame smart locks via Bluetooth Low Energy. Fully local — no hub or cloud account required.

## Supported Devices

- Sesame 4 (JP)

## Requirements

- Home Assistant with the [Bluetooth](https://www.home-assistant.io/integrations/bluetooth/) integration enabled
- A working BLE adapter (built-in or USB dongle) in range of the lock

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open the HACS repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ngoc-minh-do&repository=ha-sesame-ble&category=integration)

Or manually in HACS:

1. Open HACS → **Integrations** → **⋮** (menu) → **Custom repositories**
2. Paste `https://github.com/ngoc-minh-do/ha-sesame-ble` and select **Integration**
3. Search for **Sesame BLE** and install
4. Restart Home Assistant

### Manual

```bash
git clone https://github.com/ngoc-minh-do/ha-sesame-ble.git
cp -r ha-sesame-ble/custom_components/sesame_ble /path/to/your/ha-config/custom_components/
```

Or download the source and copy the `custom_components/sesame_ble/` folder into your Home Assistant configuration's `custom_components/` directory.

Restart Home Assistant after copying the files.

## Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration** → search for **Sesame BLE**
2. Home Assistant will scan for nearby Sesame devices. Select your lock from the list.
3. Enter the **Secret Key (SK)** from your Sesame device:
   - Open the official Sesame app
   - Go to your device's settings → **Share Key** → **QR Code**
   - Scan the QR code and extract the full content (it's a base64 string starting with `SSM`)
   - Paste it into the Home Assistant config flow

The integration will attempt a secure ECDH handshake and register your device.

## Entities

| Entity | Description |
|---|---|
| `lock.sesame_4_lock` | Lock control — supports `lock`, `unlock`, `is_locked`, `is_locking`, `is_unlocking` |
| `sensor.sesame_4_battery` | Battery level in percent |

## Configuration

Once added, you can configure the integration via **Options** (gear icon on the integration card):

| Option | Default | Description |
|---|---|---|
| Refresh interval | Off | How often to poll the lock for status updates. Options: Off, 5min, 10min, 30min, 60min |

When refresh is disabled, status updates are received on-demand when you lock/unlock, and via BLE notifications from the device.

## How It Works

The integration connects to the lock on demand (not persistently) to conserve battery on both the lock and your HA host. The protocol uses:

- **ECDH** (P-256 curve) for session key exchange
- **AES-CCM** for encrypted BLE communication
- **AES-CMAC** for message authentication

All communication is fully authenticated and encrypted using your device's secret key.
