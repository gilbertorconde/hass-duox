from typing import Any
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_LOCK_STATE_RESET,
    CONF_SCAN_INTERVAL,
    CONF_SIGNALING_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SIGNALING_SERVER_URL,
)
from .fermax_api import FermaxClient, FermaxAuthError


class DuoxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 7

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        error_info: dict[str, str] = {}

        if user_input is not None:
            try:
                session = async_get_clientsession(self.hass)
                client = FermaxClient(session)
                await client.async_login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])

                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                    options={
                        CONF_LOCK_STATE_RESET: 5
                    }
                )
            except FermaxAuthError:
                error_info['base'] = 'invalid_auth'
            except Exception:
                error_info['base'] = 'unknown'

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=error_info
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        error_info: dict[str, str] = {}

        if user_input is not None:
            try:
                entry = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, user_input[CONF_USERNAME])
                if not entry:
                    return self.async_abort(reason="entry_not_found")

                session = async_get_clientsession(self.hass)
                client = FermaxClient(session)
                await client.async_login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])

                self.hass.config_entries.async_update_entry(
                    entry=entry,
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    }
                )

                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
            except FermaxAuthError:
                error_info['base'] = 'invalid_auth'
            except Exception:
                error_info['base'] = 'unknown'

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=error_info
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DuoxOptionsFlow(config_entry)


class DuoxOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        error_info: dict[str, str] = {}

        options = self.config_entry.options
        lock_timeout = options.get(CONF_LOCK_STATE_RESET, 5)
        scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        signaling_url = options.get(CONF_SIGNALING_URL, SIGNALING_SERVER_URL)

        if user_input is not None:
            if user_input[CONF_LOCK_STATE_RESET] < 0:
                error_info['base'] = 'negative_value'
            elif user_input[CONF_SCAN_INTERVAL] < 10:
                error_info['base'] = 'scan_interval_too_low'
            else:
                if not user_input.get(CONF_SIGNALING_URL):
                    user_input[CONF_SIGNALING_URL] = SIGNALING_SERVER_URL
                self.hass.config_entries.async_update_entry(self.config_entry, options=user_input)
                return self.async_create_entry(title=None, data=None)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_LOCK_STATE_RESET, default=lock_timeout): int,
                vol.Required(CONF_SCAN_INTERVAL, default=scan_interval): int,
                vol.Optional(CONF_SIGNALING_URL, default=signaling_url): str,
            }),
            errors=error_info
        )
