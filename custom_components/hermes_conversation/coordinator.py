"""Runtime coordinator / settings holder for Hermes bridge."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .bridge_client import HermesBridgeClient
from .const import (
    CONF_BRIDGE_TOKEN,
    CONF_BRIDGE_URL,
    CONF_HERMES_PROFILE,
    CONF_TIMEOUT,
    DEFAULT_BRIDGE_URL,
    DEFAULT_HERMES_PROFILE,
    DEFAULT_TIMEOUT,
)


class HermesConversationCoordinator:
    """Small runtime object holding bridge settings and client."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """Initialize coordinator."""
        self.hass = hass
        self.bridge_url = config.get(CONF_BRIDGE_URL, DEFAULT_BRIDGE_URL)
        self.bridge_token = config.get(CONF_BRIDGE_TOKEN, "")
        self.profile = config.get(CONF_HERMES_PROFILE, DEFAULT_HERMES_PROFILE)
        self.timeout = config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        self.client = HermesBridgeClient(
            self.bridge_url, self.bridge_token, timeout=self.timeout
        )

    async def async_validate(self) -> None:
        """Validate bridge is reachable."""
        await self.client.health_check()
