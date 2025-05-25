# SystemAIR Home Assistant Integration

This integration allows you to control and monitor your Systemair ventilation unit from Home Assistant.

## Features

- Climate entity for temperature control
- Fan entity for controlling airflow and ventilation modes
- Sensors for temperatures, humidity, and air quality
- Binary sensors for system status (heating, cooling, defrosting, etc.)
- Custom services for advanced control

## Installation

1. Copy the `systemair` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Configuration > Integrations > Add Integration
4. Search for "SystemAIR" and follow the configuration flow

## Configuration

You'll need to provide your Systemair Home Solutions account credentials:

- Email address
- Password

The integration will connect to the Systemair API, authenticate, and discover your ventilation units automatically.

## Available Entities

Each ventilation unit will create the following entities:

### Climate
- Control and monitor temperature settings

### Fan
- Control ventilation mode (Auto, Manual, Crowded, Refresh, Fireplace, Away, Holiday)
- Set fan speed in manual mode

### Select
- Operation Mode select - choose between all ventilation modes

### Number
- Holiday Mode Duration - set duration for Holiday mode (in minutes)
- Away Mode Duration - set duration for Away mode (in minutes)
- Fireplace Mode Duration - set duration for Fireplace mode (in minutes)
- Refresh Mode Duration - set duration for Refresh mode (in minutes)
- Crowded Mode Duration - set duration for Crowded mode (in minutes)

### Sensors
- Room temperature
- Outdoor air temperature
- Supply air temperature
- Humidity
- Air quality
- Operation mode
- Airflow level
- Filter status

### Binary Sensors
- Heating active
- Cooling active
- Defrosting active
- Filter alarm
- ECO mode active
- Free cooling active
- Connection status

## Services

### systemair.set_user_mode
Sets the operating mode of the ventilation unit.

| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID of the ventilation unit |
| `mode` | string | Operating mode (`auto`, `manual`, `crowded`, `refresh`, `fireplace`, `away`, `holiday`) |

### systemair.set_manual_airflow
Sets the airflow level when in manual mode.

| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID of the ventilation unit |
| `airflow` | number | Airflow level (1-5) |

### systemair.set_room_temp_setpoint
Sets the temperature setpoint.

| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID of the ventilation unit |
| `temperature` | number | Temperature in °C |

### systemair.set_user_mode_time
Sets the time duration for a specific user mode.

| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID of the ventilation unit |
| `mode` | string | The mode to set time for (`holiday`, `away`, `fireplace`, `refresh`, `crowded`) |
| `time` | number | Time duration in minutes (1-1440) |

## Troubleshooting

### Debugging

Enable debug logging by adding the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.systemair: debug
```

### Common Issues

#### No devices found
- Check that your credentials are correct
- Ensure your internet connection is stable
- Verify that you have devices registered in your Systemair Home Solutions account

#### Connection problems
- The integration will automatically handle token refreshes and reconnections
- If problems persist, try removing and re-adding the integration

## Supported Devices

This integration works with any ventilation unit that is supported by the Systemair Home Solutions app.