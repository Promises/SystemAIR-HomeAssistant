"""Climate platform for SystemAIR integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    PRESET_NONE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from systemair_api.utils.constants import UserModes
from .const import DOMAIN, MODE_AUTO, MODE_MANUAL
from .coordinator import SystemairUpdateCoordinator
from .select import (
    MODE_OPTIONS,
    MODE_NAME_TO_MODE_VALUE,
    AIRFLOW_NAME_TO_LEVEL, 
    AIRFLOW_LEVEL_TO_NAME,
    AIRFLOW_SELECTABLE_OPTIONS
)

_LOGGER = logging.getLogger(__name__)

# Map SystemAIR modes to HA HVAC modes
SYSTEMAIR_TO_HVAC_MODE = {
    UserModes.AUTO: HVACMode.AUTO,
    UserModes.MANUAL: HVACMode.FAN_ONLY,
}
HVAC_TO_SYSTEMAIR_MODE = {v: k for k, v in SYSTEMAIR_TO_HVAC_MODE.items()}

# Fan mode mapping (lowercase to match HA's conventions)
FAN_MODES = ["low", "medium", "high"]  # Selectable options
FAN_MODE_TO_AIRFLOW_LEVEL = {
    "low": 2,     # Level 2 = Low
    "medium": 3,  # Level 3 = Normal
    "high": 4,    # Level 4 = High
}
AIRFLOW_LEVEL_TO_FAN_MODE = {
    1: "off",     # Level 1 = Off (not user selectable)
    2: "low",     # Level 2 = Low
    3: "medium",  # Level 3 = Normal
    4: "high",    # Level 4 = High
    5: "refresh", # Level 5 = Refresh (not user selectable)
}

# Preset mode mapping (all operation modes)
PRESET_MODES = ["auto", "manual", "crowded", "refresh", "fireplace", "away", "holiday"]
PRESET_MODE_TO_USER_MODE = {
    "auto": UserModes.AUTO,
    "manual": UserModes.MANUAL,
    "crowded": UserModes.CROWDED,
    "refresh": UserModes.REFRESH,
    "fireplace": UserModes.FIREPLACE,
    "away": UserModes.AWAY,
    "holiday": UserModes.HOLIDAY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SystemAIR climate platform."""
    coordinator: SystemairUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for unit_id, unit in coordinator.units.items():
        entities.append(SystemairClimate(coordinator, unit_id))

    async_add_entities(entities)


class SystemairClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a SystemAIR climate entity."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE |
        ClimateEntityFeature.FAN_MODE |
        ClimateEntityFeature.PRESET_MODE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.FAN_ONLY]  # We'll use preset modes instead of HVAC modes
    _attr_fan_modes = FAN_MODES  # Low, medium, high
    _attr_preset_modes = PRESET_MODES  # All special modes
    _attr_min_temp = 12
    _attr_max_temp = 28
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: SystemairUpdateCoordinator, unit_id: str) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._unit_id = unit_id
        self._unit = coordinator.units[unit_id]
        self._attr_unique_id = f"{unit_id}_climate"
        self._attr_name = f"{self._unit.name} Climate"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, unit_id)},
            "name": self._unit.name,
            "manufacturer": "Systemair",
            "model": self._unit.model or "Systemair Ventilation Unit",
            "sw_version": next((v.get("version") for v in self._unit.versions if v.get("type") == "SW"), None),
        }

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        if self._unit.temperature is not None:
            return self._unit.temperature
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self._unit.temperatures.get('setpoint') is not None:
            return self._unit.temperatures.get('setpoint')
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        # Always return FAN_ONLY as we're using preset modes instead
        return HVACMode.FAN_ONLY

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        # Return the current mode as preset
        if self._unit.user_mode is not None:
            # Convert mode value to preset mode name
            if self._unit.user_mode == UserModes.AUTO:
                return "auto"
            elif self._unit.user_mode == UserModes.MANUAL:
                return "manual"
            else:
                mode_name = self._unit.user_mode_name.lower() if self._unit.user_mode_name else None
                if mode_name in PRESET_MODES:
                    return mode_name
        return PRESET_NONE

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        if self._unit.airflow is not None:
            level = max(1, min(5, self._unit.airflow))
            return AIRFLOW_LEVEL_TO_FAN_MODE.get(level, "medium")
        return "medium"  # Default to medium

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if ATTR_TEMPERATURE in kwargs:
            # Set temperature and get result
            result = await self.hass.async_add_executor_job(
                self.coordinator.set_temperature,
                self._unit_id,
                kwargs[ATTR_TEMPERATURE],
            )
            
            # Skip immediate refresh - use optimistic update instead
            if result:
                # Use optimistic update
                self._unit.temperatures["setpoint"] = kwargs[ATTR_TEMPERATURE]
                self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        # We're not using HVAC modes anymore - no-op
        pass

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        if fan_mode in FAN_MODE_TO_AIRFLOW_LEVEL:
            level = FAN_MODE_TO_AIRFLOW_LEVEL[fan_mode]
            _LOGGER.debug(f"Setting fan mode to {fan_mode} (airflow level: {level})")
            
            # Set the fan speed and get result
            result = await self.hass.async_add_executor_job(
                self.coordinator.set_fan_speed,
                self._unit_id,
                level,
            )
            
            # Skip immediate refresh - WebSocket will update soon
            # Use optimistic update instead
            if result:
                # Use optimistic update
                self.async_write_ha_state()
        else:
            _LOGGER.error(f"Invalid fan mode: {fan_mode}")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        if preset_mode == PRESET_NONE:
            # If clearing preset, go back to auto mode
            await self.async_set_hvac_mode(HVACMode.AUTO)
            return
            
        if preset_mode in PRESET_MODE_TO_USER_MODE:
            mode_value = PRESET_MODE_TO_USER_MODE[preset_mode]
            _LOGGER.debug(f"Setting preset mode to {preset_mode} (mode value: {mode_value})")
            
            # Get default duration from config if available
            config_entry = None
            for entry_id, stored_coordinator in self.hass.data[DOMAIN].items():
                if self._unit_id in stored_coordinator.units:
                    config_entry = self.hass.config_entries.async_get_entry(entry_id)
                    break
                    
            time_minutes = None
            
            if config_entry:
                from .const import (
                    CONF_DURATION_HOLIDAY,
                    CONF_DURATION_AWAY,
                    CONF_DURATION_FIREPLACE,
                    CONF_DURATION_REFRESH,
                    CONF_DURATION_CROWDED,
                    convert_duration_to_minutes,
                )
                
                mode_to_duration_config = {
                    UserModes.HOLIDAY: CONF_DURATION_HOLIDAY,
                    UserModes.AWAY: CONF_DURATION_AWAY,
                    UserModes.FIREPLACE: CONF_DURATION_FIREPLACE,
                    UserModes.REFRESH: CONF_DURATION_REFRESH,
                    UserModes.CROWDED: CONF_DURATION_CROWDED,
                }
                
                duration_config_key = mode_to_duration_config.get(mode_value)
                if duration_config_key and duration_config_key in config_entry.data:
                    config_value = config_entry.data.get(duration_config_key)
                    time_minutes = convert_duration_to_minutes(duration_config_key, config_value)
                    _LOGGER.debug(f"Using default duration for {preset_mode} mode: {time_minutes} minutes (from {config_value} {duration_config_key.split('_')[-1]})")
            
            # Set the mode with time if available
            if time_minutes is not None:
                # Set mode with time and get result
                result = await self.hass.async_add_executor_job(
                    self.coordinator.set_mode_with_time,
                    self._unit_id,
                    mode_value,
                    time_minutes,
                )
                
                # Skip immediate refresh - use optimistic update instead
                if result:
                    # Use optimistic update
                    self._unit.user_mode = mode_value
                    self.async_write_ha_state()
            else:
                # Set mode without time and get result
                result = await self.hass.async_add_executor_job(
                    self.coordinator.set_mode,
                    self._unit_id,
                    mode_value,
                )
                
                # Skip immediate refresh - use optimistic update instead
                if result:
                    # Use optimistic update
                    self._unit.user_mode = mode_value
                    self.async_write_ha_state()
        else:
            _LOGGER.error(f"Invalid preset mode: {preset_mode}")