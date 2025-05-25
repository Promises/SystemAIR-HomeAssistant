"""Services for the SystemAIR integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

from systemair_api.utils.exceptions import SystemairError

from systemair_api.utils.constants import UserModes

from .const import (
    DOMAIN,
    SERVICE_SET_USER_MODE,
    SERVICE_SET_MANUAL_AIRFLOW,
    SERVICE_SET_ROOM_TEMP_SETPOINT,
    SERVICE_SET_USER_MODE_TIME,
    MODE_NAME_TO_VALUE,
    CONF_DURATION_HOLIDAY,
    CONF_DURATION_AWAY,
    CONF_DURATION_FIREPLACE,
    CONF_DURATION_REFRESH,
    CONF_DURATION_CROWDED,
    convert_duration_to_minutes,
)
from .coordinator import SystemairUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def _get_unit_id_from_entity(hass: HomeAssistant, entity_id: str, coordinator: SystemairUpdateCoordinator) -> str | None:
    """Get the unit ID from an entity ID."""
    entity_registry = async_get_entity_registry(hass)
    entity_entry = entity_registry.async_get(entity_id)
    if entity_entry is None or entity_entry.device_id is None:
        return None
    
    device_registry = async_get_device_registry(hass)
    device_entry = device_registry.async_get(entity_entry.device_id)
    if device_entry is None:
        return None
    
    # Look for the SystemAIR identifier in the device identifiers
    for identifier in device_entry.identifiers:
        if identifier[0] == DOMAIN:
            unit_id = identifier[1]
            if unit_id in coordinator.units:
                return unit_id
    
    return None


SET_USER_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("mode"): vol.In(list(MODE_NAME_TO_VALUE.keys())),
    }
)

SET_MANUAL_AIRFLOW_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("airflow_level"): vol.All(
            vol.Coerce(int), 
            vol.Range(min=1, max=5),
            msg="Airflow level must be between 1-5 (Off=1, Low=2, Normal=3, High=4, Refresh=5)"
        ),
    }
)

SET_ROOM_TEMP_SETPOINT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("temperature"): vol.All(vol.Coerce(float), vol.Range(min=12, max=28)),
    }
)

SET_USER_MODE_TIME_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("mode"): vol.In(["holiday", "away", "fireplace", "refresh", "crowded"]),
        vol.Required("time"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
    }
)


async def async_setup_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up the SystemAIR services."""
    try:
        coordinator: SystemairUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
        _LOGGER.debug(f"Setting up SystemAIR services with coordinator: {coordinator}")

        async def async_handle_set_user_mode(call: ServiceCall) -> None:
            """Handle the set_user_mode service call."""
            entity_id = call.data["entity_id"]
            mode_name = call.data["mode"]
            mode_value = MODE_NAME_TO_VALUE[mode_name]
            
            # Get the unit ID from the entity ID
            unit_id = await _get_unit_id_from_entity(hass, entity_id, coordinator)
            if unit_id is None:
                _LOGGER.error(f"No ventilation unit found for entity {entity_id}")
                return
            
            unit = coordinator.units.get(unit_id)
            if unit is None:
                _LOGGER.error(f"Unit {unit_id} not found in coordinator")
                return
            
            try:
                # For timed modes, get the mode key for looking up stored values
                mode_key = None
                if hasattr(unit, "get_mode_name_for_key"):
                    mode_key = unit.get_mode_name_for_key(mode_value)
                
                # Check for locally stored time value first
                time_minutes = None
                if mode_key and hasattr(unit, "user_mode_times"):
                    stored_time = unit.user_mode_times.get(mode_key)
                    if stored_time is not None:
                        time_minutes = stored_time
                        _LOGGER.debug(f"Using locally stored time for {mode_name} mode: {time_minutes} minutes")
                
                # If no stored value, fall back to configuration defaults
                if time_minutes is None:
                    # Map mode value to config key for durations
                    mode_to_duration_config = {
                        UserModes.HOLIDAY: CONF_DURATION_HOLIDAY,
                        UserModes.AWAY: CONF_DURATION_AWAY,
                        UserModes.FIREPLACE: CONF_DURATION_FIREPLACE,
                        UserModes.REFRESH: CONF_DURATION_REFRESH,
                        UserModes.CROWDED: CONF_DURATION_CROWDED,
                    }
                    
                    # If the mode is a timed mode, get the default duration from config
                    duration_config_key = mode_to_duration_config.get(mode_value)
                    if duration_config_key and duration_config_key in entry.data:
                        config_value = entry.data.get(duration_config_key)
                        time_minutes = convert_duration_to_minutes(duration_config_key, config_value)
                        _LOGGER.debug(f"Using default config duration for {mode_name} mode: {time_minutes} minutes (from {config_value} {duration_config_key.split('_')[-1]})")
                
                # Set the mode with duration if applicable
                # The coordinator's set_mode_with_time will use locally stored time
                # if time_minutes is None
                result = await hass.async_add_executor_job(
                    coordinator.set_mode_with_time, unit_id, mode_value, time_minutes
                )
                
                if result:
                    _LOGGER.debug(f"Set unit {unit_id} to mode {mode_name} ({mode_value}) with time {time_minutes} minutes")
                else:
                    _LOGGER.warning(f"Failed to set unit {unit_id} to mode {mode_name}")
                    
            except SystemairError as err:
                _LOGGER.error(f"Failed to set user mode: {err}")

        async def async_handle_set_manual_airflow(call: ServiceCall) -> None:
            """Handle the set_manual_airflow service call.
            
            Sets the airflow level according to these values:
            1 = Off (0%)
            2 = Low (25%)
            3 = Normal (50%)
            4 = High (75%)
            5 = Refresh (100%)
            """
            entity_id = call.data["entity_id"]
            airflow_level = call.data["airflow_level"]
            
            # Get the unit ID from the entity ID
            unit_id = await _get_unit_id_from_entity(hass, entity_id, coordinator)
            if unit_id is None:
                _LOGGER.error(f"No ventilation unit found for entity {entity_id}")
                return
            
            unit = coordinator.units.get(unit_id)
            if unit is None:
                _LOGGER.error(f"Unit {unit_id} not found in coordinator")
                return
            
            try:
                await hass.async_add_executor_job(
                    coordinator.set_fan_speed, unit_id, airflow_level
                )
                await coordinator.async_request_refresh()
                _LOGGER.debug(f"Set unit {unit_id} airflow level to {airflow_level}")
            except SystemairError as err:
                _LOGGER.error(f"Failed to set manual airflow: {err}")

        async def async_handle_set_room_temp_setpoint(call: ServiceCall) -> None:
            """Handle the set_room_temp_setpoint service call."""
            entity_id = call.data["entity_id"]
            temperature = call.data["temperature"]
            
            # Get the unit ID from the entity ID
            unit_id = await _get_unit_id_from_entity(hass, entity_id, coordinator)
            if unit_id is None:
                _LOGGER.error(f"No ventilation unit found for entity {entity_id}")
                return
            
            unit = coordinator.units.get(unit_id)
            if unit is None:
                _LOGGER.error(f"Unit {unit_id} not found in coordinator")
                return
            
            try:
                await hass.async_add_executor_job(
                    coordinator.set_temperature, unit_id, temperature
                )
                await coordinator.async_request_refresh()
                _LOGGER.debug(f"Set unit {unit_id} temperature setpoint to {temperature}")
            except SystemairError as err:
                _LOGGER.error(f"Failed to set temperature setpoint: {err}")

        async def async_handle_set_user_mode_time(call: ServiceCall) -> None:
            """Handle the set_user_mode_time service call.
            
            This service now stores mode durations locally for later use when the mode is activated,
            rather than sending them directly to the device.
            """
            entity_id = call.data["entity_id"]
            mode = call.data["mode"]
            time_value = call.data["time"]
            
            # Get the unit ID from the entity ID
            unit_id = await _get_unit_id_from_entity(hass, entity_id, coordinator)
            if unit_id is None:
                _LOGGER.error(f"No ventilation unit found for entity {entity_id}")
                return
            
            unit = coordinator.units.get(unit_id)
            if unit is None:
                _LOGGER.error(f"Unit {unit_id} not found in coordinator")
                return
            
            try:
                # Store the time value locally - does not send to device
                result = await hass.async_add_executor_job(
                    coordinator.set_user_mode_time, unit_id, mode, time_value
                )
                
                if result:
                    _LOGGER.debug(f"Stored {mode} mode time as {time_value} minutes for unit {unit_id}")
                    _LOGGER.debug(f"This value will be used the next time {mode} mode is activated")
                else:
                    _LOGGER.warning(f"Failed to store {mode} mode time locally")
                    
            except SystemairError as err:
                _LOGGER.error(f"Failed to store user mode time locally: {err}")

        # Register services
        hass.services.async_register(
            DOMAIN, SERVICE_SET_USER_MODE, async_handle_set_user_mode, schema=SET_USER_MODE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SET_MANUAL_AIRFLOW, async_handle_set_manual_airflow, schema=SET_MANUAL_AIRFLOW_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SET_ROOM_TEMP_SETPOINT, async_handle_set_room_temp_setpoint, schema=SET_ROOM_TEMP_SETPOINT_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SET_USER_MODE_TIME, async_handle_set_user_mode_time, schema=SET_USER_MODE_TIME_SCHEMA
        )
        
        _LOGGER.debug("Successfully registered all SystemAIR services")
    except Exception as e:
        _LOGGER.error(f"Error setting up SystemAIR services: {e}")