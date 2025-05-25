"""Config flow for SystemAIR integration."""
from __future__ import annotations

import logging
import hashlib
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from systemair_api import SystemairAuthenticator
from systemair_api.utils.exceptions import AuthenticationError, SystemairError

from .const import (
    DOMAIN,
    CONF_DURATION_HOLIDAY,
    CONF_DURATION_AWAY,
    CONF_DURATION_FIREPLACE,
    CONF_DURATION_REFRESH,
    CONF_DURATION_CROWDED,
    CONF_BASE_OPERATION_MODE,
    CONF_BASE_AIRFLOW_LEVEL,
    DEFAULT_DURATION_HOLIDAY,
    DEFAULT_DURATION_AWAY,
    DEFAULT_DURATION_FIREPLACE,
    DEFAULT_DURATION_REFRESH,
    DEFAULT_DURATION_CROWDED,
    DEFAULT_BASE_OPERATION_MODE,
    DEFAULT_BASE_AIRFLOW_LEVEL,
    MODE_NAME_TO_VALUE,
    AIRFLOW_LEVEL_TO_VALUE,
    AIRFLOW_LOW,
    AIRFLOW_NORMAL,
    AIRFLOW_HIGH,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_DURATIONS_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DURATION_HOLIDAY, default=DEFAULT_DURATION_HOLIDAY): vol.Coerce(int),    # days
        vol.Required(CONF_DURATION_AWAY, default=DEFAULT_DURATION_AWAY): vol.Coerce(int),          # hours
        vol.Required(CONF_DURATION_FIREPLACE, default=DEFAULT_DURATION_FIREPLACE): vol.Coerce(int), # minutes
        vol.Required(CONF_DURATION_REFRESH, default=DEFAULT_DURATION_REFRESH): vol.Coerce(int),     # minutes
        vol.Required(CONF_DURATION_CROWDED, default=DEFAULT_DURATION_CROWDED): vol.Coerce(int),      # hours
    }
)

STEP_BASE_OPERATION_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_OPERATION_MODE, default=DEFAULT_BASE_OPERATION_MODE): vol.In(list(MODE_NAME_TO_VALUE.keys())),
        vol.Required(CONF_BASE_AIRFLOW_LEVEL, default=DEFAULT_BASE_AIRFLOW_LEVEL): vol.In([AIRFLOW_LOW, AIRFLOW_NORMAL, AIRFLOW_HIGH]),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SystemAIR."""

    VERSION = 1
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.auth_data = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Try to connect to SystemAIR with the provided credentials
                authenticator = SystemairAuthenticator(
                    email=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                )
                await self.hass.async_add_executor_job(authenticator.authenticate)
                
                # Generate a unique ID based on the email
                # This is used instead of account_id which is not available
                unique_id = hashlib.sha256(user_input[CONF_USERNAME].encode()).hexdigest()
                
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                # Store the auth data for the next step
                self.auth_data = user_input
                
                # Proceed to duration settings
                return await self.async_step_durations()
                
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except SystemairError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
        
    async def async_step_durations(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the durations step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Validate ranges manually
            if user_input.get(CONF_DURATION_HOLIDAY, 0) < 1 or user_input.get(CONF_DURATION_HOLIDAY, 0) > 30:
                errors[CONF_DURATION_HOLIDAY] = "Holiday duration must be between 1-30 days"
            if user_input.get(CONF_DURATION_AWAY, 0) < 1 or user_input.get(CONF_DURATION_AWAY, 0) > 24:
                errors[CONF_DURATION_AWAY] = "Away duration must be between 1-24 hours"
            if user_input.get(CONF_DURATION_FIREPLACE, 0) < 1 or user_input.get(CONF_DURATION_FIREPLACE, 0) > 120:
                errors[CONF_DURATION_FIREPLACE] = "Fireplace duration must be between 1-120 minutes"
            if user_input.get(CONF_DURATION_REFRESH, 0) < 1 or user_input.get(CONF_DURATION_REFRESH, 0) > 120:
                errors[CONF_DURATION_REFRESH] = "Refresh duration must be between 1-120 minutes"
            if user_input.get(CONF_DURATION_CROWDED, 0) < 1 or user_input.get(CONF_DURATION_CROWDED, 0) > 12:
                errors[CONF_DURATION_CROWDED] = "Crowded duration must be between 1-12 hours"
            
            if not errors:
                # Store duration data and proceed to base operation step
                self.duration_data = user_input
                return await self.async_step_base_operation()
            
        return self.async_show_form(
            step_id="durations", 
            data_schema=STEP_DURATIONS_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "holiday": f"{DEFAULT_DURATION_HOLIDAY} day(s)",
                "away": f"{DEFAULT_DURATION_AWAY} hour(s)",
                "fireplace": f"{DEFAULT_DURATION_FIREPLACE} minutes",
                "refresh": f"{DEFAULT_DURATION_REFRESH} minutes",
                "crowded": f"{DEFAULT_DURATION_CROWDED} hour(s)",
            }
        )

    async def async_step_base_operation(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the base operation step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Validate that if manual mode is selected, airflow level is provided
            if user_input.get(CONF_BASE_OPERATION_MODE) == "manual":
                if user_input.get(CONF_BASE_AIRFLOW_LEVEL) not in [AIRFLOW_LOW, AIRFLOW_NORMAL, AIRFLOW_HIGH]:
                    errors[CONF_BASE_AIRFLOW_LEVEL] = "Please select a valid airflow level for manual mode"
            
            if not errors:
                # Combine all configuration data
                data = {
                    **self.auth_data, 
                    **self.duration_data, 
                    **user_input
                }
                
                return self.async_create_entry(
                    title=self.auth_data[CONF_USERNAME],
                    data=data,
                )
        
        # Create dynamic schema based on selected mode
        schema_fields = {
            vol.Required(CONF_BASE_OPERATION_MODE, default=DEFAULT_BASE_OPERATION_MODE): vol.In(list(MODE_NAME_TO_VALUE.keys())),
        }
        
        # Add airflow level field only if manual mode might be selected
        schema_fields[vol.Required(CONF_BASE_AIRFLOW_LEVEL, default=DEFAULT_BASE_AIRFLOW_LEVEL)] = vol.In([AIRFLOW_LOW, AIRFLOW_NORMAL, AIRFLOW_HIGH])
        
        return self.async_show_form(
            step_id="base_operation",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "note": "Manual mode requires an airflow level. Other modes use automatic airflow control.",
                "airflow_levels": "Low (25%), Normal (50%), High (75%)",
            }
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle SystemAIR options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return await self.async_step_durations()

    async def async_step_durations(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle duration options."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Validate ranges manually
            if user_input.get(CONF_DURATION_HOLIDAY, 0) < 1 or user_input.get(CONF_DURATION_HOLIDAY, 0) > 30:
                errors[CONF_DURATION_HOLIDAY] = "Holiday duration must be between 1-30 days"
            if user_input.get(CONF_DURATION_AWAY, 0) < 1 or user_input.get(CONF_DURATION_AWAY, 0) > 24:
                errors[CONF_DURATION_AWAY] = "Away duration must be between 1-24 hours"
            if user_input.get(CONF_DURATION_FIREPLACE, 0) < 1 or user_input.get(CONF_DURATION_FIREPLACE, 0) > 120:
                errors[CONF_DURATION_FIREPLACE] = "Fireplace duration must be between 1-120 minutes"
            if user_input.get(CONF_DURATION_REFRESH, 0) < 1 or user_input.get(CONF_DURATION_REFRESH, 0) > 120:
                errors[CONF_DURATION_REFRESH] = "Refresh duration must be between 1-120 minutes"
            if user_input.get(CONF_DURATION_CROWDED, 0) < 1 or user_input.get(CONF_DURATION_CROWDED, 0) > 12:
                errors[CONF_DURATION_CROWDED] = "Crowded duration must be between 1-12 hours"
            
            if not errors:
                # Store duration data and proceed to base operation step
                self.duration_data = user_input
                return await self.async_step_base_operation()
            
        # Get current values from config entry
        current_data = self.config_entry.data
        schema = vol.Schema({
            vol.Required(
                CONF_DURATION_HOLIDAY, 
                default=current_data.get(CONF_DURATION_HOLIDAY, DEFAULT_DURATION_HOLIDAY)
            ): vol.Coerce(int),
            vol.Required(
                CONF_DURATION_AWAY, 
                default=current_data.get(CONF_DURATION_AWAY, DEFAULT_DURATION_AWAY)
            ): vol.Coerce(int),
            vol.Required(
                CONF_DURATION_FIREPLACE, 
                default=current_data.get(CONF_DURATION_FIREPLACE, DEFAULT_DURATION_FIREPLACE)
            ): vol.Coerce(int),
            vol.Required(
                CONF_DURATION_REFRESH, 
                default=current_data.get(CONF_DURATION_REFRESH, DEFAULT_DURATION_REFRESH)
            ): vol.Coerce(int),
            vol.Required(
                CONF_DURATION_CROWDED, 
                default=current_data.get(CONF_DURATION_CROWDED, DEFAULT_DURATION_CROWDED)
            ): vol.Coerce(int),
        })
            
        return self.async_show_form(
            step_id="durations", 
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "holiday": f"{DEFAULT_DURATION_HOLIDAY} day(s)",
                "away": f"{DEFAULT_DURATION_AWAY} hour(s)",
                "fireplace": f"{DEFAULT_DURATION_FIREPLACE} minutes",
                "refresh": f"{DEFAULT_DURATION_REFRESH} minutes",
                "crowded": f"{DEFAULT_DURATION_CROWDED} hour(s)",
            }
        )

    async def async_step_base_operation(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle base operation options."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Validate that if manual mode is selected, airflow level is provided
            if user_input.get(CONF_BASE_OPERATION_MODE) == "manual":
                if user_input.get(CONF_BASE_AIRFLOW_LEVEL) not in [AIRFLOW_LOW, AIRFLOW_NORMAL, AIRFLOW_HIGH]:
                    errors[CONF_BASE_AIRFLOW_LEVEL] = "Please select a valid airflow level for manual mode"
            
            if not errors:
                # Combine all data and update the config entry
                new_data = {
                    **self.config_entry.data,
                    **self.duration_data,
                    **user_input
                }
                
                return self.async_create_entry(title="", data=new_data)
        
        # Get current values from config entry
        current_data = self.config_entry.data
        schema_fields = {
            vol.Required(
                CONF_BASE_OPERATION_MODE, 
                default=current_data.get(CONF_BASE_OPERATION_MODE, DEFAULT_BASE_OPERATION_MODE)
            ): vol.In(list(MODE_NAME_TO_VALUE.keys())),
            vol.Required(
                CONF_BASE_AIRFLOW_LEVEL, 
                default=current_data.get(CONF_BASE_AIRFLOW_LEVEL, DEFAULT_BASE_AIRFLOW_LEVEL)
            ): vol.In([AIRFLOW_LOW, AIRFLOW_NORMAL, AIRFLOW_HIGH]),
        }
        
        return self.async_show_form(
            step_id="base_operation",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "note": "Manual mode requires an airflow level. Other modes use automatic airflow control.",
                "airflow_levels": "Low (25%), Normal (50%), High (75%)",
            }
        )