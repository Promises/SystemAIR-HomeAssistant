"""The SystemAIR integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import SystemairUpdateCoordinator
from .services import async_setup_services

DOMAIN = "systemair"
_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SystemAIR from a config entry."""
    coordinator = SystemairUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Load saved time values from storage
    try:
        await coordinator.async_load_stored_time_values()
        _LOGGER.debug("Loaded stored mode time values from disk")
    except Exception as err:
        _LOGGER.warning(f"Failed to load stored time values: {err}")
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Set up services
    await async_setup_services(hass, entry)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Save time values to storage before unloading
    try:
        await coordinator.async_save_stored_time_values()
        _LOGGER.debug("Saved mode time values to disk")
    except Exception as err:
        _LOGGER.warning(f"Failed to save time values: {err}")
    
    # Disconnect the WebSocket if it exists
    if coordinator.websocket:
        _LOGGER.debug("Disconnecting from SystemAIR WebSocket")
        await hass.async_add_executor_job(coordinator.websocket.disconnect)
    
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    
    # Unregister services
    for service in [
        "set_user_mode", 
        "set_manual_airflow", 
        "set_room_temp_setpoint",
        "set_user_mode_time"
    ]:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
    
    return unload_ok