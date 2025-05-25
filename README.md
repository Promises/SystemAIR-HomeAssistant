# SystemAIR Home Assistant Integration

A Home Assistant custom component for SystemAIR ventilation units that provides comprehensive monitoring and control capabilities.

## Features

- **Real-time monitoring** via WebSocket connection
- **Control ventilation modes** (Auto, Manual, Crowded, Refresh, Fireplace, Away, Holiday)
- **Adjustable airflow levels** (1-10)
- **Temperature monitoring** (supply, extract, outdoor, exhaust)
- **Air quality monitoring** (humidity, CO2, pressure)
- **Status indicators** (heating, cooling, defrosting, filter status)
- **Duration configuration** for timed modes with proper time units:
  - REFRESH: minutes
  - CROWDED: hours  
  - FIREPLACE: minutes
  - AWAY: hours
  - HOLIDAY: days

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Install the SystemAIR integration
3. Restart Home Assistant
4. Go to Settings → Devices & Services → Add Integration
5. Search for "SystemAIR" and configure with your credentials

### Manual Installation

1. Copy the `custom_components/systemair` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Add the integration through the UI

## Configuration

The integration is configured through the Home Assistant UI:

1. Go to Settings → Devices & Services
2. Click "Add Integration" 
3. Search for "SystemAIR"
4. Enter your SystemAIR Home Solutions credentials
5. Configure duration settings for timed modes

## Requirements

- SystemAIR Home Solutions account
- SystemAIR ventilation unit connected to the cloud service
- Home Assistant 2023.1 or later

## Dependencies

This integration uses the [systemair-api-promises](https://pypi.org/project/systemair-api-promises/) Python library for communication with the SystemAIR API.

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/henningbe/systemair-ha-component/issues).

## License

This project is licensed under the MIT License - see the LICENSE file for details.