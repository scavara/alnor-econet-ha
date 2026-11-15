"""Config flow for Alnor ecoNet HRU."""
from __future__ import annotations

from collections.abc import Mapping
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

    async def _async_check_login(self, email: str, password: str) -> bool:
        try:
            await self.hass.async_add_executor_job(_validate_login, email, password)
        except Exception:  # noqa: BLE001
            return False
        return True

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user change the account email/password of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if await self._async_check_login(
                user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            ):
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
            errors["base"] = "invalid_auth"

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=entry.data[CONF_EMAIL]): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Started by Home Assistant when the stored password stops working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if await self._async_check_login(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            ):
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
            errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
