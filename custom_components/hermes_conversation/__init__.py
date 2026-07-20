"""The Hermes Conversation integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import HermesConversationCoordinator

PLATFORMS: tuple[Platform, ...] = (Platform.CONVERSATION,)
_LOGGER = logging.getLogger(__name__)

HermesConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: HermesConfigEntry) -> bool:
    """Set up Hermes Conversation from a config entry."""
    coordinator = HermesConversationCoordinator(hass, dict(entry.data))
    try:
        await coordinator.async_validate()
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Failed to reach Hermes bridge: %s", err)
        raise ConfigEntryNotReady(f"Bridge unreachable: {err}") from err

    setattr(entry, "runtime_data", coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HermesConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
