"""Fan platform for SystemAIR integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from systemair_api.utils.constants import UserModes
from .const import (
    DOMAIN,
    FAN_SPEED_1,
    FAN_SPEED_2,
    FAN_SPEED_3,
    FAN_SPEED_4,
    FAN_SPEED_5,
    FAN_SPEED_AUTO,
    FAN_SPEED_TO_VALUE,
    MODE_AUTO,
    MODE_MANUAL,
)
from .coordinator import SystemairUpdateCoordinator

ORDERED_SPEEDS = [FAN_SPEED_1, FAN_SPEED_2, FAN_SPEED_3, FAN_SPEED_4, FAN_SPEED_5]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SystemAIR fan platform."""
    coordinator: SystemairUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for unit_id, unit in coordinator.units.items():
        entities.append(SystemairFan(coordinator, unit_id))

    async_add_entities(entities)


class SystemairFan(CoordinatorEntity, FanEntity):
    """Representation of a SystemAIR fan entity."""

    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
    _attr_preset_modes = ["auto", "manual", "crowded", "refresh", "fireplace", "away", "holiday"]
    _attr_speed_count = len(ORDERED_SPEEDS)

    def __init__(self, coordinator: SystemairUpdateCoordinator, unit_id: str) -> None:
        """Initialize the fan entity."""
        super().__init__(coordinator)
        self._unit_id = unit_id
        self._unit = coordinator.units[unit_id]
        self._attr_unique_id = f"{unit_id}_fan"
        self._attr_name = f"{self._unit.name} Fan"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, unit_id)},
            "name": self._unit.name,
            "manufacturer": "Systemair",
            "model": self._unit.model or "Systemair Ventilation Unit",
            "sw_version": next((v.get("version") for v in self._unit.versions if v.get("type") == "SW"), None),
        }

    @property
    def is_on(self) -> bool:
        """Return true if fan is on."""
        # Fan is on unless it's in mode 5 (away) or 6 (holiday)
        return self._unit.user_mode < 5

    @property
    def percentage(self) -> int | None:
        """Return the fan percentage speed."""
        # Return percentage based on airflow level regardless of mode
        if self._unit.airflow is not None:
            # Convert airflow to a 1-5 scale
            airflow_level = max(1, min(5, self._unit.airflow // 20))
            return ordered_list_item_to_percentage(
                ORDERED_SPEEDS, 
                ORDERED_SPEEDS[airflow_level - 1]
            )
        return None

    @property
    def preset_mode(self) -> str | None:
        """Return the fan preset mode."""
        if self._unit.user_mode is not None:
            # Map user mode values to preset mode names
            mode_mapping = {
                UserModes.AUTO: "auto",
                UserModes.MANUAL: "manual",
                UserModes.CROWDED: "crowded",
                UserModes.REFRESH: "refresh",
                UserModes.FIREPLACE: "fireplace",
                UserModes.AWAY: "away",
                UserModes.HOLIDAY: "holiday",
            }
            return mode_mapping.get(self._unit.user_mode)
        return None

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the fan speed percentage."""
        # Set the speed based on percentage, independent of mode
        speed_name = percentage_to_ordered_list_item(ORDERED_SPEEDS, percentage)
        speed_value = FAN_SPEED_TO_VALUE.get(speed_name, 3)  # Default to 3 if not found
        
        await self.hass.async_add_executor_job(
            self.coordinator.set_fan_speed, self._unit_id, speed_value
        )
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the fan preset mode."""
        # Map preset modes to UserModes
        mode_mapping = {
            "auto": UserModes.AUTO,
            "manual": UserModes.MANUAL,
            "crowded": UserModes.CROWDED,
            "refresh": UserModes.REFRESH,
            "fireplace": UserModes.FIREPLACE,
            "away": UserModes.AWAY,
            "holiday": UserModes.HOLIDAY,
        }
        
        if preset_mode in mode_mapping:
            mode_value = mode_mapping[preset_mode]
            
            # Get default time duration for timed modes
            time_minutes = None
            config_entry = None
            
            # Find the config entry for this device
            for entry_id, coordinator in self.hass.data[DOMAIN].items():
                if self._unit_id in coordinator.units:
                    config_entry = self.hass.config_entries.async_get_entry(entry_id)
                    break
                    
            # Map mode value to config key for durations
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
                
                # If the mode is a timed mode, get the default duration from config
                duration_config_key = mode_to_duration_config.get(mode_value)
                if duration_config_key and duration_config_key in config_entry.data:
                    config_value = config_entry.data.get(duration_config_key)
                    time_minutes = convert_duration_to_minutes(duration_config_key, config_value)
                    self.coordinator._LOGGER.debug(f"Using default duration for {preset_mode} mode: {time_minutes} minutes (from {config_value} {duration_config_key.split('_')[-1]})")
                    
            # Use set_mode_with_time if we have a time value, otherwise use set_mode
            if time_minutes is not None:
                await self.hass.async_add_executor_job(
                    self.coordinator.set_mode_with_time, self._unit_id, mode_value, time_minutes
                )
            else:
                await self.hass.async_add_executor_job(
                    self.coordinator.set_mode, self._unit_id, mode_value
                )
                
            await self.coordinator.async_request_refresh()

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        """Turn on the fan."""
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            # Default to auto mode when turning on
            # Use set_preset_mode so it handles any duration settings
            await self.async_set_preset_mode("auto")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan (set to away mode)."""
        # Use set_preset_mode so it handles any duration settings
        await self.async_set_preset_mode("away")