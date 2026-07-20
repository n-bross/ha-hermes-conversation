"""Diagnostics for Hermes Conversation integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ROUTING_MODE, DEFAULT_ROUTING_MODE
from .coordinator import HermesConversationCoordinator


async def async_get_config_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: HermesConversationCoordinator = getattr(entry, "runtime_data")
    return {
        "bridge_url": coordinator.bridge_url,
        "profile": coordinator.profile,
        "timeout": coordinator.timeout,
        "routing_mode": entry.data.get(CONF_ROUTING_MODE, DEFAULT_ROUTING_MODE),
        "authenticated": bool(coordinator.bridge_token),
    }
