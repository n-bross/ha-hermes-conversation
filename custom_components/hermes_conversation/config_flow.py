"""Config flow for Hermes Conversation integration."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .bridge_client import (
    HermesBridgeAuthError,
    HermesBridgeClient,
    HermesBridgeError,
    HermesBridgeTimeout,
)
from .const import (
    CONF_BRIDGE_TOKEN,
    CONF_BRIDGE_URL,
    CONF_HERMES_PROFILE,
    CONF_ROUTING_MODE,
    CONF_TIMEOUT,
    DEFAULT_BRIDGE_URL,
    DEFAULT_HERMES_PROFILE,
    DEFAULT_ROUTING_MODE,
    DEFAULT_TIMEOUT,
    DOMAIN,
    ROUTING_MODES,
)

_LOGGER = logging.getLogger(__name__)


class HermesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hermes Conversation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            bridge_url = user_input[CONF_BRIDGE_URL].rstrip("/")
            token = user_input[CONF_BRIDGE_TOKEN]
            timeout = user_input[CONF_TIMEOUT]

            client = HermesBridgeClient(bridge_url, token, timeout=timeout)
            try:
                await client.health_check()
            except HermesBridgeAuthError:
                errors["base"] = "invalid_auth"
            except HermesBridgeTimeout:
                errors["base"] = "timeout"
            except HermesBridgeError:
                errors["base"] = "cannot_connect"
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Unexpected error checking bridge: %s", err)
                errors["base"] = "unknown"
            finally:
                await client.async_close()

            if not errors:
                await self.async_set_unique_id(
                    f"{bridge_url}_{user_input[CONF_HERMES_PROFILE]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Hermes Conversation",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_BRIDGE_URL, default=DEFAULT_BRIDGE_URL): str,
                vol.Required(CONF_BRIDGE_TOKEN): str,
                vol.Required(CONF_HERMES_PROFILE, default=DEFAULT_HERMES_PROFILE): str,
                vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
                vol.Optional(CONF_ROUTING_MODE, default=DEFAULT_ROUTING_MODE): vol.In(
                    ROUTING_MODES
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HermesOptionsFlowHandler:
        """Get the options flow."""
        return HermesOptionsFlowHandler(config_entry)


class HermesOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow for Hermes Conversation."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = dict(self.config_entry.data)
        options = dict(self.config_entry.options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TIMEOUT,
                    default=options.get(CONF_TIMEOUT, data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
                ): int,
                vol.Optional(
                    CONF_ROUTING_MODE,
                    default=options.get(
                        CONF_ROUTING_MODE,
                        data.get(CONF_ROUTING_MODE, DEFAULT_ROUTING_MODE),
                    ),
                ): vol.In(ROUTING_MODES),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
