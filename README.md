# HASS-Duox

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

## Description

Custom Home Assistant integration for **Fermax Duox** intercoms.
Control your door, monitor connection status, WiFi signal, and receive doorbell ring notifications — all from Home Assistant using the official Fermax API.

## Features

- **Open Door**: Unlock your building door via Home Assistant (lock entity).
- **F1 Button**: Trigger the F1 relay function (button entity).
- **Connection Status**: Monitor whether your intercom is connected (binary sensor).
- **WiFi Signal**: See your intercom's WiFi signal strength (sensor).
- **Doorbell Ring**: Real-time doorbell ring detection via FCM push notifications (binary sensor).
- **Multiple Doors**: Supports devices with multiple access points.
- **Token Management**: Handles authentication and automatic token refreshing.
- **Config Flow**: Easy setup via Home Assistant UI.

## Installation

### Option 1: HACS (Recommended)
1. Open HACS in Home Assistant.
2. Go to "Integrations" > "Explore & Download Repositories".
3. Add this repository URL as a custom repository: `https://github.com/gilbertorconde/hass-duox`
4. Search for "Fermax Duox" and click "Download".
5. Restart Home Assistant.

### Option 2: Manual
1. Copy the `custom_components/duox` folder to your HA `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings** > **Devices & Services**.
2. Click **Add Integration**.
3. Search for **Fermax Duox**.
4. Enter your Fermax Duox **Username** and **Password**.

## Disclaimer

This integration is not affiliated with Fermax. Use at your own risk.

## Acknowledgements

Based on work by:
- [patrikulus/hass-bluecon](https://github.com/patrikulus/hass-bluecon) - Working fork that this project builds upon
- [AfonsoFGarcia/hass-bluecon](https://github.com/AfonsoFGarcia/hass-bluecon) - Original Fermax Blue integration
- [marcosav/fermax-blue-intercom](https://github.com/marcosav/fermax-blue-intercom) - Fermax Blue API reverse engineering

## License
MIT License | [Read more here](LICENSE)
