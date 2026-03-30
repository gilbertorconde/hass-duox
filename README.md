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

### Mobile Notifications

Get push notifications on your phone when someone rings the doorbell — repeated ringing like a phone call, with auto-connect to the live feed. Handles the full call lifecycle: ring, answered on another device, missed, and ended.

**Prerequisites:** Install the [Home Assistant Companion App](https://companion.home-assistant.io/) on your Android/iOS phone and connect it to your HA instance.

#### 1. Create a Doorbell Dashboard

1. Go to **Settings** > **Dashboards** > **Add Dashboard**.
2. Set Title: `Doorbell`, Icon: `mdi:doorbell-video`, URL: `doorbell`.
3. Open the new dashboard, edit it, and add the intercom card (see [Intercom Card Setup](#intercom-card-setup) above).

#### 2. Import the Blueprint

Click the button below to import the doorbell notification blueprint:

[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/gilbertorconde/hass-duox/blob/main/blueprints/automation/duox_doorbell_notification.yaml)

Or go to **Settings** > **Automations & Scenes** > **Blueprints** > **Import Blueprint** and paste:
```
https://github.com/gilbertorconde/hass-duox/blob/main/blueprints/automation/duox_doorbell_notification.yaml
```

#### 3. Create the Automation from the Blueprint

1. Go to **Settings** > **Automations & Scenes** > **Create Automation** > **Use a Blueprint**.
2. Select **Duox Doorbell Notification**.
3. Configure the inputs:

| Input | Required | Description |
|-------|----------|-------------|
| Doorbell sensor | Yes | Your `binary_sensor.duox_doorbell_*` entity. |
| Camera entity | No | `camera.duox_doorbell_camera` for snapshot in notifications. |
| Notify device 1 | Yes | Your phone (must have the HA Companion App). |
| Notify device 2-3 | No | Additional phones to notify. |
| Intercom dashboard path | No | Dashboard path for the tap action (default: `/dashboard-doorbell/0`). |
| Auto-connect on tap | No | Start video feed automatically when tapping the notification (default: on). |
| Timeout | No | Seconds to keep ringing before marking as missed (default: 90). |
| Ring interval | No | Seconds between repeated ring notifications (default: 8). |

4. Save the automation.

#### 4. Customize the Notification Sound

After receiving the first notification, go to your phone's **Settings** > **Apps** > **Home Assistant** > **Notifications** > **doorbell** channel and set a distinctive ringtone.

**How it works:** The blueprint sends a high-priority notification that repeats every N seconds (like a phone call ringing). If someone answers on another device, the notification is replaced with "Call answered". If no one answers, it becomes "Missed call". Tapping the ringing notification opens your intercom dashboard and auto-connects to the live video feed.

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
