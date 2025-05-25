"""Constants for the SystemAIR integration."""

DOMAIN = "systemair"

# Services
SERVICE_SET_USER_MODE = "set_user_mode"
SERVICE_SET_MANUAL_AIRFLOW = "set_manual_airflow"
SERVICE_SET_ROOM_TEMP_SETPOINT = "set_room_temp_setpoint"
SERVICE_SET_USER_MODE_TIME = "set_user_mode_time"

# Config constants
CONF_DEFAULT_MODE_DURATIONS = "default_mode_durations"
CONF_DURATION_HOLIDAY = "duration_holiday"
CONF_DURATION_AWAY = "duration_away"
CONF_DURATION_FIREPLACE = "duration_fireplace"
CONF_DURATION_REFRESH = "duration_refresh"
CONF_DURATION_CROWDED = "duration_crowded"
CONF_BASE_OPERATION_MODE = "base_operation_mode"
CONF_BASE_AIRFLOW_LEVEL = "base_airflow_level"

# Default durations - stored in their natural units
DEFAULT_DURATION_HOLIDAY = 1      # 1 day
DEFAULT_DURATION_AWAY = 2         # 2 hours
DEFAULT_DURATION_FIREPLACE = 15   # 15 minutes
DEFAULT_DURATION_REFRESH = 30     # 30 minutes
DEFAULT_DURATION_CROWDED = 1      # 1 hour

# Base operation defaults
DEFAULT_BASE_OPERATION_MODE = "manual"
DEFAULT_BASE_AIRFLOW_LEVEL = "normal"

# User modes
MODE_AUTO = 0
MODE_MANUAL = 1
MODE_CROWDED = 2
MODE_REFRESH = 3
MODE_FIREPLACE = 4
MODE_AWAY = 5
MODE_HOLIDAY = 6

# Fan modes
FAN_SPEED_AUTO = "auto"
FAN_SPEED_1 = "speed_1"
FAN_SPEED_2 = "speed_2"
FAN_SPEED_3 = "speed_3"
FAN_SPEED_4 = "speed_4"
FAN_SPEED_5 = "speed_5"

# Airflow levels for manual mode
AIRFLOW_LOW = "low"
AIRFLOW_NORMAL = "normal"
AIRFLOW_HIGH = "high"

# Maps fan speed names to speed values
FAN_SPEED_TO_VALUE = {
    FAN_SPEED_1: 1,
    FAN_SPEED_2: 2,
    FAN_SPEED_3: 3,
    FAN_SPEED_4: 4,
    FAN_SPEED_5: 5,
}

# Maps airflow level names to airflow values for manual mode
AIRFLOW_LEVEL_TO_VALUE = {
    AIRFLOW_LOW: 2,      # Low = 25%
    AIRFLOW_NORMAL: 3,   # Normal = 50%
    AIRFLOW_HIGH: 4,     # High = 75%
}

# Maps mode names to mode values
MODE_NAME_TO_VALUE = {
    "auto": MODE_AUTO,
    "manual": MODE_MANUAL,
    "crowded": MODE_CROWDED,
    "refresh": MODE_REFRESH,
    "fireplace": MODE_FIREPLACE,
    "away": MODE_AWAY,
    "holiday": MODE_HOLIDAY,
}

def convert_duration_to_minutes(duration_config_key: str, value: int) -> int:
    """Convert duration value to minutes based on the config key.
    
    This is for Home Assistant internal use where we need minutes.
    """
    if duration_config_key == CONF_DURATION_HOLIDAY:
        return value * 24 * 60  # days to minutes
    elif duration_config_key in [CONF_DURATION_AWAY, CONF_DURATION_CROWDED]:
        return value * 60  # hours to minutes
    elif duration_config_key in [CONF_DURATION_FIREPLACE, CONF_DURATION_REFRESH]:
        return value  # already in minutes
    else:
        return value  # fallback

def convert_duration_to_api_units(duration_config_key: str, value: int) -> int:
    """Convert duration value to the units expected by the API registers.
    
    API expects:
    - HOLIDAY: days (REG_MAINBOARD_USERMODE_HOLIDAY_TIME = 251)
    - AWAY: hours (REG_MAINBOARD_USERMODE_AWAY_TIME = 252) 
    - FIREPLACE: minutes (REG_MAINBOARD_USERMODE_FIREPLACE_TIME = 253)
    - REFRESH: minutes (REG_MAINBOARD_USERMODE_REFRESH_TIME = 254)
    - CROWDED: hours (REG_MAINBOARD_USERMODE_CROWDED_TIME = 255)
    """
    # Config values are already in their natural units, which matches what API expects
    return value