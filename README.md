# HASS-Duox

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

## Description

Custom Home Assistant integration for **Fermax Duox** intercoms.
Full intercom experience from Home Assistant — open doors, view live video, have two-way audio conversations, receive real-time doorbell notifications, and browse call history, all using the official Fermax cloud API.

## Features

### Core Entities
- **Open Door** — Unlock your building door via Home Assistant (lock entity).
- **F1 Button** — Trigger the F1 relay function (button entity).
- **Connection Status** — Monitor whether your intercom is connected (binary sensor).
- **WiFi Signal** — See your intercom's WiFi signal strength (sensor with states: terrible, bad, weak, good, excellent).
- **Doorbell Ring** — Real-time doorbell ring detection via FCM push notifications (binary sensor).
- **Doorbell Camera** — Snapshot camera entity that captures the last doorbell photo.

### Live Intercom (Custom Lovelace Card)
- **Live Video** — View the doorbell camera feed in real-time via WebRTC (mediasoup).
- **Bidirectional Audio** — Full two-way intercom: talk and listen through Home Assistant.
- **On-Demand View** — Initiate a call to the panel from HA (autoon) without waiting for someone to ring.
- **Gate Unlock** — Open the door directly from the intercom card while viewing the feed.
- **Call History** — Browse past calls in a bottom sheet modal (picked up, missed, autoon) fetched from the Fermax API. Tap an entry to view its snapshot photo.
- **WiFi Indicator** — Live WiFi signal strength icon overlaid on the video area.
- **Last Snapshot** — Shows the most recent doorbell photo when no call is active, with an overlay badge.

### Infrastructure
- **Multiple Doors** — Supports devices with multiple access points.
- **Token Management** — Handles authentication and automatic token refreshing.
- **Config Flow** — Easy setup via Home Assistant UI.
- **HACS Compatible** — Install and update via HACS.

## Installation

### Option 1: HACS (Recommended)
1. Open HACS in Home Assistant.
2. Go to **Integrations** > three-dot menu > **Custom repositories**.
3. Add this repository URL: `https://github.com/gilbertorconde/hass-duox`
4. Category: **Integration**.
5. Search for "Fermax Duox" and click **Download**.
6. Restart Home Assistant.

### Option 2: Manual
1. Copy the `custom_components/duox` folder to your HA `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

### Integration Setup
1. Go to **Settings** > **Devices & Services**.
2. Click **Add Integration**.
3. Search for **Fermax Duox**.
4. Enter your Fermax Duox **Username** and **Password**.

### Intercom Card Setup

Add the custom Lovelace card to your dashboard. The card JavaScript is automatically registered when the integration loads.

```yaml
type: custom:duox-intercom-card
entry_id: "<your_config_entry_id>"
camera_entity: camera.duox_doorbell_camera
lock_entity: lock.duox_main
wifi_entity: sensor.duox_wifi_signal
device_name: "Front Door"
```

| Option | Required | Description |
|--------|----------|-------------|
| `entry_id` | Yes | The config entry ID for your Duox integration (find it in the URL when viewing the integration). |
| `camera_entity` | No | Camera entity for snapshot display when idle. |
| `lock_entity` | No | Lock entity to show a gate-unlock button on the card. |
| `wifi_entity` | No | WiFi signal sensor entity to show a signal indicator on the card. |
| `device_name` | No | Human-readable name shown in call history entries (default: "Doorbell"). |

### Recommended Logging (for troubleshooting)

```yaml
logger:
  default: warning
  logs:
    custom_components.duox: debug
```

## How It Works

### Doorbell Notifications
The integration registers as an Android device with Firebase Cloud Messaging (FCM) using the Fermax app's Firebase credentials. When someone rings your doorbell, the Fermax cloud sends a push notification that the integration receives in real-time, triggering the doorbell binary sensor and capturing call metadata for the live video feed.

### Live Video & Audio
Video and audio use **mediasoup** (a WebRTC SFU) with **Socket.IO** for signaling — the same infrastructure as the official Fermax app. The custom Lovelace card loads `mediasoup-client` and `socket.io-client` from CDN, connects to the Fermax signaling server, and establishes WebRTC transports for receiving video/audio and sending microphone audio.

### On-Demand View (Autoon)
When you press "Connect" on the card without an active doorbell ring, the integration calls the Fermax `autoon` API (v2) to initiate a call to the panel. The panel camera activates, and the Fermax cloud sends an FCM notification back with the streaming room details. The card then connects to the live feed.

### Call History
The card can fetch call history from the Fermax call registry API, showing past calls with their status (picked up, missed, autoon) and timestamps in a sliding bottom sheet. Tap any entry that has a photo to view the snapshot from that call.

## Entities Created

| Entity | Type | Description |
|--------|------|-------------|
| `lock.duox_*` | Lock | Door opener for each access point |
| `button.duox_f1` | Button | F1 relay trigger |
| `binary_sensor.duox_connection` | Binary Sensor | Device connectivity status |
| `binary_sensor.duox_doorbell_*` | Binary Sensor | Doorbell ring detection (one per door) |
| `sensor.duox_wifi_signal` | Sensor | WiFi signal strength (enum) |
| `camera.duox_doorbell_camera` | Camera | Last doorbell snapshot |

## Disclaimer

This integration is not affiliated with Fermax. It uses the official Fermax cloud API endpoints as reverse-engineered from the Fermax DuoxMe Android app. Use at your own risk.

## Acknowledgements

Built upon work by:
- [patrikulus/hass-bluecon](https://github.com/patrikulus/hass-bluecon) — Working fork that this project was originally based on
- [AfonsoFGarcia/hass-bluecon](https://github.com/AfonsoFGarcia/hass-bluecon) — Original Fermax Blue integration
- [marcosav/fermax-blue-intercom](https://github.com/marcosav/fermax-blue-intercom) — Fermax Blue API reverse engineering

## License

MIT License | [Read more here](LICENSE)
