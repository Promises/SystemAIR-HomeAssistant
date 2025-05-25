"""Select platform for SystemAIR integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, Final

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from systemair_api.utils.constants import UserModes
from systemair_api.models.ventilation_unit import VentilationUnit

from .const import DOMAIN, MODE_NAME_TO_VALUE
from .coordinator import SystemairUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Define a mapping of mode values to friendly names
MODE_OPTIONS: Dict[int, str] = {
    UserModes.AUTO: "Auto",
    UserModes.MANUAL: "Manual",
    UserModes.CROWDED: "Crowded",
    UserModes.REFRESH: "Refresh",
    UserModes.FIREPLACE: "Fireplace",
    UserModes.AWAY: "Away", 
    UserModes.HOLIDAY: "Holiday",
}

# Airflow level options for the select entity
AIRFLOW_LEVEL_OPTIONS = ["Off", "Low", "Normal", "High", "Refresh"]

# Options that can be selected by the user (excludes Off and Refresh)
AIRFLOW_SELECTABLE_OPTIONS = ["Low", "Normal", "High", "Refresh"]

# Mapping from level name to value (1-5)
AIRFLOW_NAME_TO_LEVEL = {
    "Off": 1,
    "Low": 2, 
    "Normal": 3,
    "High": 4,
    "Refresh": 5
}

# Mapping from level value to name
AIRFLOW_LEVEL_TO_NAME = {v: k for k, v in AIRFLOW_NAME_TO_LEVEL.items()}

# Reverse mapping for lookup
MODE_NAME_TO_MODE_VALUE = {v: k for k, v in MODE_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SystemAIR select entities."""
    coordinator: SystemairUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for unit_id, unit in coordinator.units.items():
        # Add operation mode select entity
        entities.append(SystemairOperationModeSelect(coordinator, unit_id))
        
        # Add airflow level select entity
        entities.append(SystemairAirflowLevelSelect(coordinator, unit_id))

    async_add_entities(entities)


class SystemairOperationModeSelect(CoordinatorEntity, SelectEntity):
    """Representation of a SystemAIR operation mode select entity."""

    _attr_has_entity_name = True
    _attr_name = "Operation Mode"
    _attr_icon = "mdi:fan-speed-3"
    _attr_options = list(MODE_OPTIONS.values())

    def __init__(self, coordinator: SystemairUpdateCoordinator, unit_id: str) -> None:
        """Initialize the operation mode select entity."""
        super().__init__(coordinator)
        self._unit_id = unit_id
        self._unit = coordinator.units[unit_id]
        self._attr_unique_id = f"{unit_id}_operation_mode_select"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, unit_id)},
            "name": self._unit.name,
            "manufacturer": "Systemair",
            "model": self._unit.model or "Systemair Ventilation Unit",
            "sw_version": next((v.get("version") for v in self._unit.versions if v.get("type") == "SW"), None),
        }

    @property
    def current_option(self) -> str | None:
        """Return the current selected operation mode."""
        if self._unit.user_mode is not None and self._unit.user_mode in MODE_OPTIONS:
            return MODE_OPTIONS[self._unit.user_mode]
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in MODE_NAME_TO_MODE_VALUE:
            _LOGGER.error(f"Unknown operation mode: {option}")
            return

        mode_value = MODE_NAME_TO_MODE_VALUE[option]
        
        # Set mode and get result
        result = await self.hass.async_add_executor_job(
            self.coordinator.set_mode, self._unit_id, mode_value
        )
        
        # Skip immediate refresh - use optimistic update instead
        if result:
            # Use optimistic update
            self._unit.user_mode = mode_value
            self.async_write_ha_state()


class SystemairAirflowLevelSelect(CoordinatorEntity, SelectEntity):
    """Representation of a SystemAIR airflow level select entity."""

    _attr_has_entity_name = True
    _attr_name = "Airflow Level"
    _attr_icon = "mdi:fan"
    _attr_options = AIRFLOW_LEVEL_OPTIONS  # Keep full options list for display
    _attr_selectable = False  # Non-standard attribute for template use

    def __init__(self, coordinator: SystemairUpdateCoordinator, unit_id: str) -> None:
        """Initialize the airflow level select entity."""
        super().__init__(coordinator)
        self._unit_id = unit_id
        self._unit = coordinator.units[unit_id]
        self._attr_unique_id = f"{unit_id}_airflow_level_select"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, unit_id)},
            "name": self._unit.name,
            "manufacturer": "Systemair",
            "model": self._unit.model or "Systemair Ventilation Unit",
            "sw_version": next((v.get("version") for v in self._unit.versions if v.get("type") == "SW"), None),
        }

    @property
    def current_option(self) -> str | None:
        """Return the current selected airflow level."""
        if self._unit.airflow is not None:
            # Make sure the airflow value is within valid range (1-5)
            level = max(1, min(5, self._unit.airflow))
            _LOGGER.debug(f"Airflow level for {self._unit_id}: {level}")
            return AIRFLOW_LEVEL_TO_NAME.get(level, "Normal")  # Default to Normal if not found
        return None
        
    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes about the airflow level."""
        current = self.current_option
        return {
            "selectable_options": AIRFLOW_SELECTABLE_OPTIONS,
            "is_selectable": current in AIRFLOW_SELECTABLE_OPTIONS,
            "level": AIRFLOW_NAME_TO_LEVEL.get(current, 3),
            "mode": self._unit.user_mode_name.lower() if self._unit.user_mode_name else "unknown"
        }

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Restrict selection to the allowed options
        if option not in AIRFLOW_SELECTABLE_OPTIONS:
            _LOGGER.error(f"Cannot select restricted airflow level: {option}")
            return
        
        if option not in AIRFLOW_NAME_TO_LEVEL:
            _LOGGER.error(f"Unknown airflow level: {option}")
            return

        level = AIRFLOW_NAME_TO_LEVEL[option]
        _LOGGER.debug(f"Setting airflow level to {level} ({option})")
        
        # Special handling for Refresh level
        if option == "Refresh":
            _LOGGER.debug("Special handling for Refresh mode")
            # Set the ventilation unit to Refresh mode
            from systemair_api.utils.constants import UserModes
            
            # Check for configured duration
            config_entry = None
            time_minutes = None
            
            # Find the config entry for this device
            for entry_id, coordinator in self.hass.data[DOMAIN].items():
                if self._unit_id in coordinator.units:
                    config_entry = self.hass.config_entries.async_get_entry(entry_id)
                    break
                    
            # Get refresh duration from config
            if config_entry:
                from .const import CONF_DURATION_REFRESH, convert_duration_to_minutes
                if CONF_DURATION_REFRESH in config_entry.data:
                    config_value = config_entry.data.get(CONF_DURATION_REFRESH)
                    time_minutes = convert_duration_to_minutes(CONF_DURATION_REFRESH, config_value)
                    _LOGGER.debug(f"Using configured Refresh duration: {time_minutes} minutes (from {config_value} minutes)")
                    
            # Set refresh mode with time if available
            if time_minutes is not None:
                result = await self.hass.async_add_executor_job(
                    self.coordinator.set_mode_with_time,
                    self._unit_id,
                    UserModes.REFRESH,
                    time_minutes
                )
            else:
                # No configured time, just set the mode
                result = await self.hass.async_add_executor_job(
                    self.coordinator.set_mode,
                    self._unit_id,
                    UserModes.REFRESH
                )
                
            # Optimistic update
            if result:
                self._unit.user_mode = UserModes.REFRESH
                self._unit.airflow = level  # Also update airflow level
                self.async_write_ha_state()
                
        else:
            # For Low, Medium, High - set to Manual mode first if needed
            # then set the airflow level
            _LOGGER.debug(f"Setting to Manual mode with airflow level {level}")
            from systemair_api.utils.constants import UserModes
            
            set_manual_first = False
            # If not already in Manual mode, we need to switch to Manual first
            if self._unit.user_mode != UserModes.MANUAL:
                set_manual_first = True
                
            if set_manual_first:
                # First set to Manual mode
                mode_result = await self.hass.async_add_executor_job(
                    self.coordinator.set_mode, self._unit_id, UserModes.MANUAL
                )
                
                if not mode_result:
                    _LOGGER.error(f"Failed to set mode to Manual before setting airflow level")
                    return
                
                # Update unit mode for optimistic update
                self._unit.user_mode = UserModes.MANUAL
            
            # Then set the airflow level
            result = await self.hass.async_add_executor_job(
                self.coordinator.set_fan_speed, self._unit_id, level
            )
            
            # Skip immediate refresh - use optimistic update instead
            if result:
                # Use optimistic update
                self._unit.airflow = level
                self.async_write_ha_state()