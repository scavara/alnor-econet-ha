"""Config flow for Alnor ecoNet HRU."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    CLIENT_ID,
    CONF_EMAIL,
    CONF_FACTORY_NUMBER,
    CONF_INSTALLATION_ID,
    CONF_PASSWORD,
    DOMAIN,
    REGION,
    USER_POOL_ID,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_INSTALLATION_ID): str,
        vol.Required(CONF_FACTORY_NUMBER): str,
    }
)


def _validate_login(email: str, password: str) -> None:
    """Blocking Cognito auth check; raises on failure."""
    from pycognito import Cognito

    u = Cognito(USER_POOL_ID, CLIENT_ID, username=email, user_pool_region=REGION)
    u.authenticate(password=password)


class AlnorEconetConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Alnor ecoNet."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_FACTORY_NUMBER])
            self._abort_if_unique_id_configured()
            try:
                await self.hass.async_add_executor_job(
                    _validate_login,
                    user_input[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                )
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_auth"
            else:
                return self.async_create_entry(
                    title=f"Alnor HRU {user_input[CONF_FACTORY_NUMBER]}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
