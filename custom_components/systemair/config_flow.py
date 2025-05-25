"""Config flow for SystemAIR integration."""
from __future__ import annotations

import logging
import hashlib
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
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
    DEFAULT_DURATION_HOLIDAY,
    DEFAULT_DURATION_AWAY,
    DEFAULT_DURATION_FIREPLACE,
    DEFAULT_DURATION_REFRESH,
    DEFAULT_DURATION_CROWDED,
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


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SystemAIR."""

    VERSION = 1

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
                # Combine auth data with duration settings
                data = {**self.auth_data, **user_input}
                
                return self.async_create_entry(
                    title=self.auth_data[CONF_USERNAME],
                    data=data,
                )
            
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


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""