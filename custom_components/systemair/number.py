"""Number entities for SystemAIR ventilation units."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Callable

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from systemair_api.models.ventilation_unit import VentilationUnit

from .const import DOMAIN, MODE_MANUAL, FAN_SPEED_TO_VALUE
from .coordinator import SystemairUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Define entity descriptions for mode times - these are config values, not device values
MODE_TIME_DESCRIPTIONS = [
    NumberEntityDescription(
        key="holiday",
        name="Holiday Mode Duration",
        icon="mdi:beach",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_step=1,
        native_unit_of_measurement="d",
    ),
    NumberEntityDescription(
        key="away",
        name="Away Mode Duration",
        icon="mdi:home-export-outline",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_step=1,
        native_unit_of_measurement="h",
    ),
    NumberEntityDescription(
        key="fireplace",
        name="Fireplace Mode Duration",
        icon="mdi:fireplace",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_step=5,
        native_unit_of_measurement="min",
    ),
    NumberEntityDescription(
        key="refresh",
        name="Refresh Mode Duration",
        icon="mdi:refresh",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_step=5,
        native_unit_of_measurement="min",
    ),
    NumberEntityDescription(
        key="crowded",
        name="Crowded Mode Duration",
        icon="mdi:account-group",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_step=1,
        native_unit_of_measurement="h",
    ),
]

# We removed the airflow level number entity in favor of a select entity

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator: SystemairUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    # Create number entities for each unit
    for unit_id, unit in coordinator.units.items():
        # Add mode time entities
        for description in MODE_TIME_DESCRIPTIONS:
            entities.append(SystemairModeTimeEntity(coordinator, unit_id, description))
        
        # Airflow level entity is now a select entity, not a number entity
            
    async_add_entities(entities)


class SystemairModeTimeEntity(CoordinatorEntity, NumberEntity):
    """Entity representing a ventilation mode time setting."""

    def __init__(
        self,
        coordinator: SystemairUpdateCoordinator,
        unit_id: str,
        description: NumberEntityDescription,
    ) -> None:
        """Initialize the mode time entity."""
        super().__init__(coordinator)
        self.unit_id = unit_id
        self.entity_description = description
        self._unit: VentilationUnit = coordinator.units[unit_id]
        self._attr_unique_id = f"{unit_id}_{description.key}_mode_time"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, unit_id)},
            "name": self._unit.name,
            "manufacturer": "Systemair",
            "model": self._unit.model or "Ventilation Unit",
        }
    
    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self._unit.name} {self.entity_description.name}"
    
    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return self.coordinator.available and self.unit_id in self.coordinator.units
    
    @property
    def native_value(self) -> int:
        """Return the current configuration value."""
        mode_key = self.entity_description.key
        
        # Get values from configuration entry, not from device
        config_entry = None
        for entry_id, coordinator in self.hass.data[DOMAIN].items():
            if self.unit_id in coordinator.units:
                config_entry = self.hass.config_entries.async_get_entry(entry_id)
                break
        
        if config_entry:
            from .const import (
                CONF_DURATION_HOLIDAY,
                CONF_DURATION_AWAY, 
                CONF_DURATION_FIREPLACE,
                CONF_DURATION_REFRESH,
                CONF_DURATION_CROWDED,
            )
            
            # Map mode keys to config keys
            mode_to_config = {
                'holiday': CONF_DURATION_HOLIDAY,
                'away': CONF_DURATION_AWAY,
                'fireplace': CONF_DURATION_FIREPLACE,
                'refresh': CONF_DURATION_REFRESH,
                'crowded': CONF_DURATION_CROWDED,
            }
            
            config_key = mode_to_config.get(mode_key)
            if config_key and config_key in config_entry.data:
                return int(config_entry.data[config_key])
        
        # Fallback to defaults
        from .const import (
            DEFAULT_DURATION_HOLIDAY,
            DEFAULT_DURATION_AWAY,
            DEFAULT_DURATION_FIREPLACE, 
            DEFAULT_DURATION_REFRESH,
            DEFAULT_DURATION_CROWDED,
        )
        
        defaults = {
            'holiday': DEFAULT_DURATION_HOLIDAY,
            'away': DEFAULT_DURATION_AWAY,
            'fireplace': DEFAULT_DURATION_FIREPLACE,
            'refresh': DEFAULT_DURATION_REFRESH,
            'crowded': DEFAULT_DURATION_CROWDED,
        }
        
        return int(defaults.get(mode_key, 0))
            
    def get_mode_name_for_key(self, mode_value: int) -> str:
        """Map numeric mode value to string mode key."""
        from systemair_api.utils.constants import UserModes
        mode_map = {
            UserModes.HOLIDAY: "holiday",
            UserModes.AWAY: "away",
            UserModes.FIREPLACE: "fireplace",
            UserModes.REFRESH: "refresh",
            UserModes.CROWDED: "crowded"
        }
        return mode_map.get(mode_value, "")
    
    async def async_set_native_value(self, value: float) -> None:
        """Update the configuration value."""
        mode_key = self.entity_description.key
        new_value = int(value)
        
        # Find the config entry for this device
        config_entry = None
        for entry_id, coordinator in self.hass.data[DOMAIN].items():
            if self.unit_id in coordinator.units:
                config_entry = self.hass.config_entries.async_get_entry(entry_id)
                break
        
        if config_entry:
            from .const import (
                CONF_DURATION_HOLIDAY,
                CONF_DURATION_AWAY,
                CONF_DURATION_FIREPLACE,
                CONF_DURATION_REFRESH,
                CONF_DURATION_CROWDED,
            )
            
            # Map mode keys to config keys
            mode_to_config = {
                'holiday': CONF_DURATION_HOLIDAY,
                'away': CONF_DURATION_AWAY,
                'fireplace': CONF_DURATION_FIREPLACE,
                'refresh': CONF_DURATION_REFRESH,
                'crowded': CONF_DURATION_CROWDED,
            }
            
            config_key = mode_to_config.get(mode_key)
            if config_key:
                # Validate the value based on the mode
                valid = True
                if mode_key == 'holiday' and not (1 <= new_value <= 30):
                    valid = False
                elif mode_key in ['away', 'crowded'] and not (1 <= new_value <= 24 if mode_key == 'away' else 1 <= new_value <= 12):
                    valid = False
                elif mode_key in ['fireplace', 'refresh'] and not (1 <= new_value <= 120):
                    valid = False
                
                if valid:
                    # Update the config entry data
                    new_data = dict(config_entry.data)
                    new_data[config_key] = new_value
                    
                    self.hass.config_entries.async_update_entry(
                        config_entry, data=new_data
                    )
                    
                    # Update the UI
                    self.async_write_ha_state()
                    
                    unit_name = "days" if mode_key == 'holiday' else ("hours" if mode_key in ['away', 'crowded'] else "minutes")
                    _LOGGER.debug(f"Updated {mode_key} mode duration to {new_value} {unit_name}")
                else:
                    _LOGGER.error(f"Invalid value {new_value} for {mode_key} mode duration")
            else:
                _LOGGER.error(f"Unknown mode key: {mode_key}")
        else:
            _LOGGER.error(f"Could not find config entry for unit {self.unit_id}")


# The airflow level entity is now a select entity instead of a number entity