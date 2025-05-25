"""Data update coordinator for the SystemAIR integration."""
from __future__ import annotations

import asyncio
import logging
import json
import os
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store

from systemair_api import SystemairAPI, SystemairAuthenticator, VentilationUnit
from systemair_api.api.websocket_client import SystemairWebSocket
from systemair_api.utils.exceptions import SystemairError, TokenRefreshError, APIError
from systemair_api.utils.constants import UserModes

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=30)


class SystemairUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching SystemAIR data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry_id = entry.entry_id
        self.authenticator = SystemairAuthenticator(
            email=entry.data["username"],
            password=entry.data["password"],
        )
        self.api = None
        self.websocket = None
        self.units: Dict[str, VentilationUnit] = {}
        self.available = False
        
        # Setup storage for time values
        self.storage = Store(hass, 1, f"systemair.{entry.entry_id}.time_values")
        self._stored_time_values = {}
        
        super().__init__(
            hass,
            _LOGGER,
            name="SystemAIR",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, VentilationUnit]:
        """Fetch data from SystemAIR API."""
        try:
            # Authenticate if needed
            if not self.api:
                _LOGGER.debug("Authenticating with SystemAIR API")
                await self.hass.async_add_executor_job(self.authenticator.authenticate)
                
                # Create API instance with the access token
                self.api = SystemairAPI(access_token=self.authenticator.access_token)
                
                # Fetch ventilation units
                devices_response = await self.hass.async_add_executor_job(self.api.get_account_devices)
                
                # Process devices into VentilationUnit objects
                # Debug log the entire response to understand its structure
                _LOGGER.info(f"API Response: {devices_response}")
                
                # Check for errors in the response
                if 'errors' in devices_response:
                    _LOGGER.error(f"API returned errors: {devices_response['errors']}")
                
                # Try different possible response structures
                # First try: { "data": { "GetAccountDevices": [ array of devices ] } }
                # Second try: { "data": { "account": { "devices": [ array of devices ] } } }
                data = devices_response.get("data", {})
                
                # Try to find devices in the response using multiple possible paths
                devices = None
                
                # Try first structure path
                if "GetAccountDevices" in data:
                    devices = data.get("GetAccountDevices", [])
                    _LOGGER.debug("Found devices using path: data.GetAccountDevices")
                
                # Try second structure path 
                elif "account" in data and "devices" in data.get("account", {}):
                    devices = data.get("account", {}).get("devices", [])
                    _LOGGER.debug("Found devices using path: data.account.devices")
                
                # If still no devices, log details and paths tried
                if not devices:
                    devices = []
                    _LOGGER.warning("No devices found in API response. Data structure might be different than expected.")
                    _LOGGER.info(f"Response data keys: {data.keys()}")
                    if "account" in data:
                        _LOGGER.info(f"Account keys: {data.get('account', {}).keys()}")
                
                _LOGGER.info(f"Found devices in API response: {devices}")
                
                for device in devices:
                    # The API might use "identifier" or "id" - try both
                    device_id = device.get("identifier") or device.get("id")
                    device_name = device.get("name")
                    
                    # Log the device details for debugging
                    _LOGGER.info(f"Device found: ID={device_id}, Name={device_name}, Keys={device.keys()}")
                    
                    if device_id and device_name:
                        # Create VentilationUnit instance
                        unit = VentilationUnit(device_id, device_name)
                        
                        # Try to get device status
                        try:
                            status = await self.hass.async_add_executor_job(
                                self.api.fetch_device_status, device_id
                            )
                            unit.update_from_api(status)
                        except Exception as ex:
                            _LOGGER.warning(f"Failed to fetch initial status for {device_name}: {ex}")
                            
                        # Add to units dictionary
                        self.units[device_id] = unit
                
                # Setup WebSocket connection for real-time updates
                try:
                    # Create a callback function to handle websocket messages
                    def handle_ws_message(message: Dict[str, Any]) -> None:
                        """Handle incoming WebSocket messages."""
                        _LOGGER.debug(f"Received WebSocket message: {message}")
                        
                        # Check if this is a device status update message
                        if message.get("action") == "DEVICE_STATUS_UPDATE" and message.get("type") == "SYSTEM_EVENT":
                            # Extract the device ID from the 'id' field in properties
                            properties = message.get("properties", {})
                            device_id = properties.get("id")
                            
                            if device_id and device_id in self.units:
                                _LOGGER.debug(f"Updating unit {device_id} from WebSocket")
                                self.units[device_id].update_from_websocket(message)
                                
                                # Schedule an immediate update through the Home Assistant event loop
                                # This safely triggers entity updates from the WebSocket data
                                _LOGGER.debug(f"Unit {device_id} updated from WebSocket, scheduling immediate refresh")
                                self.hass.loop.call_soon_threadsafe(
                                    lambda: self.hass.create_task(
                                        self.async_refresh()
                                    )
                                )
                            elif device_id:
                                _LOGGER.debug(f"Received update for unknown device ID: {device_id}")
                        # Check for the original message format too
                        elif "identifier" in message and message["identifier"] in self.units:
                            unit_id = message["identifier"]
                            self.units[unit_id].update_from_websocket(message)
                            
                            # Schedule an immediate update through the Home Assistant event loop
                            # This safely triggers entity updates from the WebSocket data
                            _LOGGER.debug(f"Unit {unit_id} updated from WebSocket, scheduling immediate refresh")
                            self.hass.loop.call_soon_threadsafe(
                                lambda: self.hass.create_task(
                                    self.async_refresh()
                                )
                            )
                        else:
                            _LOGGER.debug(f"Received WebSocket message of type: {message.get('type')}, action: {message.get('action')}")
                    
                    # Initialize the WebSocket client
                    self.websocket = SystemairWebSocket(
                        access_token=self.authenticator.access_token,
                        on_message_callback=handle_ws_message
                    )
                    
                    # Connect to the WebSocket in an executor
                    await self.hass.async_add_executor_job(self.websocket.connect)
                    _LOGGER.debug("WebSocket connection established")
                    
                except Exception as ex:
                    _LOGGER.warning(f"Failed to connect WebSocket: {ex}")
                
                self.available = True
                _LOGGER.debug(f"Found {len(self.units)} ventilation units")
                
            # Check if token needs refresh
            if not self.authenticator.is_token_valid():
                _LOGGER.debug("Refreshing auth token")
                await self.hass.async_add_executor_job(self.authenticator.refresh_access_token)
                self.api.update_token(self.authenticator.access_token)
                
                # If we have a WebSocket connection, recreate it with the new token
                if self.websocket:
                    _LOGGER.debug("Reconnecting WebSocket with new token")
                    await self.hass.async_add_executor_job(self.websocket.disconnect)
                    
                    # Initialize the WebSocket client with the new token
                    def handle_ws_message(message):
                        """Handle incoming WebSocket messages."""
                        _LOGGER.debug(f"Received WebSocket message: {message}")
                        
                        # Check if this is a device status update message
                        if message.get("action") == "DEVICE_STATUS_UPDATE" and message.get("type") == "SYSTEM_EVENT":
                            # Extract the device ID from the 'id' field in properties
                            properties = message.get("properties", {})
                            device_id = properties.get("id")
                            
                            if device_id and device_id in self.units:
                                _LOGGER.debug(f"Updating unit {device_id} from WebSocket")
                                self.units[device_id].update_from_websocket(message)
                                
                                # Schedule an immediate update through the Home Assistant event loop
                                # This safely triggers entity updates from the WebSocket data
                                _LOGGER.debug(f"Unit {device_id} updated from WebSocket, scheduling immediate refresh")
                                self.hass.loop.call_soon_threadsafe(
                                    lambda: self.hass.create_task(
                                        self.async_refresh()
                                    )
                                )
                            elif device_id:
                                _LOGGER.debug(f"Received update for unknown device ID: {device_id}")
                        # Check for the original message format too
                        elif "identifier" in message and message["identifier"] in self.units:
                            unit_id = message["identifier"]
                            self.units[unit_id].update_from_websocket(message)
                            
                            # Schedule an immediate update through the Home Assistant event loop
                            # This safely triggers entity updates from the WebSocket data
                            _LOGGER.debug(f"Unit {unit_id} updated from WebSocket, scheduling immediate refresh")
                            self.hass.loop.call_soon_threadsafe(
                                lambda: self.hass.create_task(
                                    self.async_refresh()
                                )
                            )
                        else:
                            _LOGGER.debug(f"Received WebSocket message of type: {message.get('type')}, action: {message.get('action')}")
                    
                    self.websocket = SystemairWebSocket(
                        access_token=self.authenticator.access_token,
                        on_message_callback=handle_ws_message
                    )
                    
                    await self.hass.async_add_executor_job(self.websocket.connect)
                    _LOGGER.debug("WebSocket reconnected")
                
            # Update unit data by fetching latest status
            for unit_id, unit in self.units.items():
                try:
                    status = await self.hass.async_add_executor_job(
                        self.api.fetch_device_status, unit_id
                    )
                    unit.update_from_api(status)
                    _LOGGER.debug(f"Updated unit {unit_id} from API: airflow={unit.airflow}, mode={unit.user_mode}")
                except Exception as ex:
                    _LOGGER.warning(f"Failed to update unit {unit_id}: {ex}")
            
            # Return a dictionary with the unit data
            return {unit_id: unit for unit_id, unit in self.units.items()}
        
        except (SystemairError, TokenRefreshError, APIError) as err:
            self.available = False
            _LOGGER.error(f"Error communicating with SystemAIR API: {err}")
            raise UpdateFailed(f"Error communicating with SystemAIR API: {err}") from err
    
    def set_mode(self, unit_id: str, mode: int) -> bool:
        """Set the operation mode.
        
        For timed modes, this will use set_mode_with_time to ensure time values are sent.
        
        Returns:
            bool: True if successful, False otherwise
        """
        from systemair_api.utils.constants import UserModes
        
        # For timed modes, use set_mode_with_time to ensure time registers are set
        timed_modes = {UserModes.HOLIDAY, UserModes.AWAY, UserModes.FIREPLACE, UserModes.REFRESH, UserModes.CROWDED}
        
        if mode in timed_modes:
            # Use set_mode_with_time which will handle time values automatically
            return self.set_mode_with_time(unit_id, mode, None)
        else:
            # For non-timed modes (AUTO, MANUAL), use direct mode setting
            unit = self.units.get(unit_id)
            if unit and self.api:
                try:
                    result = unit.set_user_mode(self.api, mode)
                    if result:
                        # Update local state for optimistic updates
                        unit.user_mode = mode
                    return result
                except Exception as err:
                    _LOGGER.error(f"Failed to set mode: {err}")
            return False
                
    def set_mode_with_time(self, unit_id: str, mode: int, time_minutes: Optional[int] = None) -> bool:
        """Set the operation mode with an optional time duration.
        
        If time_minutes is not provided, it will use the stored value for the mode.
        
        Args:
            unit_id: The ID of the ventilation unit
            mode: The mode to set
            time_minutes: Optional time duration in minutes, if None will use locally stored value
            
        Returns:
            bool: True if successful, False otherwise
        """
        unit = self.units.get(unit_id)
        if unit and self.api:
            try:
                # Get the mode name for key to check stored time values
                mode_key = ""
                if hasattr(unit, 'get_mode_name_for_key'):
                    mode_key = unit.get_mode_name_for_key(mode)
                else:
                    # Fallback implementation
                    from systemair_api.utils.constants import UserModes as UM
                    mode_map = {
                        UM.HOLIDAY: "holiday",
                        UM.AWAY: "away",
                        UM.FIREPLACE: "fireplace", 
                        UM.REFRESH: "refresh",
                        UM.CROWDED: "crowded"
                    }
                    mode_key = mode_map.get(mode, "")
                    _LOGGER.warning(f"VentilationUnit missing get_mode_name_for_key method, using fallback for mode {mode}")
                
                _LOGGER.debug(f"Mode key for mode {mode}: {mode_key}")
                
                # If time_minutes wasn't provided, check if we have a stored value for this mode
                if time_minutes is None and hasattr(unit, "user_mode_times") and mode_key:
                    stored_time = unit.user_mode_times.get(mode_key)
                    if stored_time is not None:
                        time_minutes = stored_time
                        _LOGGER.debug(f"Using stored time value of {time_minutes} minutes for mode {mode_key}")
                
                # If still no time_minutes, fall back to configuration defaults
                if time_minutes is None:
                    from systemair_api.utils.constants import UserModes as UM2
                    from .const import (
                        CONF_DURATION_HOLIDAY,
                        CONF_DURATION_AWAY,
                        CONF_DURATION_FIREPLACE,
                        CONF_DURATION_REFRESH,
                        CONF_DURATION_CROWDED,
                        convert_duration_to_minutes,
                    )
                    
                    # Find the config entry for this device
                    config_entry = None
                    for entry_id, coordinator in self.hass.data[DOMAIN].items():
                        if unit_id in coordinator.units:
                            config_entry = self.hass.config_entries.async_get_entry(entry_id)
                            break
                    
                    if config_entry:
                        # Map mode value to config key for durations
                        mode_to_duration_config = {
                            UM2.HOLIDAY: CONF_DURATION_HOLIDAY,
                            UM2.AWAY: CONF_DURATION_AWAY,
                            UM2.FIREPLACE: CONF_DURATION_FIREPLACE,
                            UM2.REFRESH: CONF_DURATION_REFRESH,
                            UM2.CROWDED: CONF_DURATION_CROWDED,
                        }
                        
                        # If the mode is a timed mode, get the default duration from config
                        duration_config_key = mode_to_duration_config.get(mode)
                        if duration_config_key and duration_config_key in config_entry.data:
                            config_value = config_entry.data.get(duration_config_key)
                            time_minutes = convert_duration_to_minutes(duration_config_key, config_value)
                            _LOGGER.debug(f"Using config default duration for {mode_key} mode: {time_minutes} minutes (from {config_value} {duration_config_key.split('_')[-1]})")
                
                result = False
                # Check if the unit supports the new set_user_mode method with time parameter
                try:
                    # Try to call with time parameter
                    result = unit.set_user_mode(self.api, mode, time_minutes)
                    if result:
                        # Update local state for optimistic updates
                        unit.user_mode = mode
                        # If we used a time value, record it for future reference
                        if hasattr(unit, "user_mode_times") and time_minutes is not None and mode_key:
                            unit.user_mode_times[mode_key] = time_minutes
                            _LOGGER.debug(f"Mode {mode_key} activated with duration of {time_minutes} minutes")
                            # Save the time value to persistent storage
                            self.hass.async_create_task(self.async_save_stored_time_values())
                except TypeError:
                    # Fall back to old method if TypeError occurs (wrong number of arguments)
                    result = unit.set_user_mode(self.api, mode)
                    if result:
                        # Update local state for optimistic updates
                        unit.user_mode = mode
                    _LOGGER.warning("This version of SystemAIR-API doesn't support setting mode time together with mode. Update the package for full functionality.")
                return result
            except Exception as err:
                _LOGGER.error(f"Failed to set mode with time: {err}")
        return False
    
    def set_fan_speed(self, unit_id: str, speed: int) -> bool:
        """Set the fan speed, independent of user mode.
        
        Args:
            unit_id: The ID of the ventilation unit
            speed: The desired fan speed (1-5)
            
        Returns:
            bool: True if successful, False otherwise
        """
        from systemair_api.utils.register_constants import RegisterConstants
        
        _LOGGER.debug(f"Setting fan speed for unit {unit_id} to {speed}")
        unit = self.units.get(unit_id)
        if unit and self.api:
            try:
                # The airflow level is an enum (1-5), use the exact value
                # Level 1 = Off
                # Level 2 = Low
                # Level 3 = Normal
                # Level 4 = High
                # Level 5 = Refresh
                
                # Validate input is between 1-5
                airflow_value = max(1, min(5, speed))
                _LOGGER.debug(f"Using direct airflow enum value: {airflow_value}")
                _LOGGER.debug(f"Setting airflow level to {airflow_value}")
                
                # Set the airflow level using the correct register
                register = RegisterConstants.REG_MAINBOARD_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF
                _LOGGER.debug(f"Using register {register} (REG_MAINBOARD_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF)")
                
                # Check current mode
                _LOGGER.debug(f"Current user mode before setting airflow: {unit.user_mode}")
                
                result = unit.set_value(
                    self.api, 
                    register, 
                    airflow_value,
                    True
                )
                
                if result:
                    _LOGGER.debug(f"Successfully set airflow level for {unit_id} to {airflow_value}")
                    # Manually update the airflow value in the unit instance for immediate feedback
                    unit.airflow = airflow_value
                    _LOGGER.debug(f"Updated unit.airflow to level {unit.airflow}")
                    return True
                else:
                    _LOGGER.warning(f"Failed to set fan speed for {unit_id}")
                    
            except Exception as err:
                _LOGGER.error(f"Failed to set fan speed: {err}")
                
        return False
    
    def set_temperature(self, unit_id: str, temperature: float) -> bool:
        """Set the temperature setpoint.
        
        Returns:
            bool: True if successful, False otherwise
        """
        unit = self.units.get(unit_id)
        if unit and self.api:
            try:
                # Convert temperature to tenths of degrees as expected by the API
                temp_tenths = int(temperature * 10)
                result = unit.set_temperature(self.api, temp_tenths)
                
                if result:
                    # Update local state for optimistic updates
                    unit.temperatures["setpoint"] = temperature
                return result
            except Exception as err:
                _LOGGER.error(f"Failed to set temperature: {err}")
        return False
                
    async def async_load_stored_time_values(self) -> None:
        """Load stored time values from disk."""
        stored_data = await self.storage.async_load()
        if stored_data:
            self._stored_time_values = stored_data
            _LOGGER.debug(f"Loaded stored time values: {self._stored_time_values}")
            
            # Apply stored values to units if they exist
            for unit_id, mode_times in self._stored_time_values.items():
                if unit_id in self.units and hasattr(self.units[unit_id], "user_mode_times"):
                    for mode, time_value in mode_times.items():
                        self.units[unit_id].user_mode_times[mode] = time_value
                    _LOGGER.debug(f"Applied stored time values to unit {unit_id}")
    
    async def async_save_stored_time_values(self) -> None:
        """Save time values to disk."""
        # Build the data to save from the units' current values
        data_to_save = {}
        for unit_id, unit in self.units.items():
            if hasattr(unit, "user_mode_times"):
                data_to_save[unit_id] = dict(unit.user_mode_times)
        
        # Save to disk
        await self.storage.async_save(data_to_save)
        self._stored_time_values = data_to_save
        _LOGGER.debug(f"Saved time values to storage: {data_to_save}")
    
    def set_user_mode_time(self, unit_id: str, mode: str, time_value: int) -> bool:
        """Store the time duration for a specific user mode locally without sending to device.
        
        The time values are only stored locally and used when activating modes later.
        These values are not sent to the device until the mode is activated.
        
        Args:
            unit_id: The ID of the ventilation unit
            mode: The mode to set time for ('holiday', 'away', 'fireplace', 'refresh', 'crowded')
            time_value: The time duration in minutes
            
        Returns:
            bool: True if successful, False otherwise
        """
        unit = self.units.get(unit_id)
        if unit:
            try:
                # Store locally without sending to the API
                if hasattr(unit, "user_mode_times"):
                    # Update local state only
                    unit.user_mode_times[mode] = time_value
                    _LOGGER.debug(f"Stored {mode} mode time locally as {time_value} minutes for unit {unit_id}")
                    
                    # Schedule saving to persistent storage
                    self.hass.async_create_task(self.async_save_stored_time_values())
                    return True
                else:
                    _LOGGER.warning(f"Unit {unit_id} doesn't have user_mode_times attribute, can't store time value")
            except Exception as err:
                _LOGGER.error(f"Failed to store user mode time locally: {err}")
        return False