"""Hermes ConversationEntity for Home Assistant Assist."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.util import ulid

from .bridge_client import (
    HermesBridgeAuthError,
    HermesBridgeError,
    HermesBridgeTimeout,
    HermesBridgeUnavailable,
)
from .const import DOMAIN
from .coordinator import HermesConversationCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: conversation.AddEntitiesCallback,
) -> None:
    """Set up Hermes conversation agent."""
    coordinator: HermesConversationCoordinator = getattr(entry, "runtime_data")
    async_add_entities([HermesConversationEntity(coordinator, entry)])


class HermesConversationEntity(
    conversation.ConversationEntity, conversation.AbstractConversationAgent
):
    """Hermes-backed Assist agent."""

    _attr_attribution = "Hermes Agent"
    _attr_name = "Hermes"

    def __init__(
        self, coordinator: HermesConversationCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the entity."""
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = entry.entry_id

    @property
    def supported_languages(self) -> list[str]:
        """Return supported languages."""
        return ["*"]

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a user request via the Hermes bridge."""
        conversation_id = user_input.conversation_id or ulid.ulid_now()

        user_name = user_input.context.user_name
        user_id = user_input.context.user_id
        device_id = user_input.device_id
        language = user_input.language or "en"

        try:
            data = await self.coordinator.client.send_request(
                text=user_input.text,
                conversation_id=conversation_id,
                language=language,
                user_name=user_name,
                user_id=user_id,
                device_id=device_id,
            )
        except HermesBridgeTimeout:
            _LOGGER.error("Hermes bridge request timed out")
            return self._error_result(
                conversation_id,
                "The Hermes bridge did not respond in time.",
            )
        except HermesBridgeAuthError:
            _LOGGER.error("Hermes bridge authentication failed")
            return self._error_result(
                conversation_id,
                "Authentication with the Hermes bridge failed.",
            )
        except HermesBridgeUnavailable:
            _LOGGER.error("Hermes bridge is unavailable")
            return self._error_result(
                conversation_id,
                "The Hermes bridge is offline.",
            )
        except HermesBridgeError as err:
            _LOGGER.error("Hermes bridge error: %s", err)
            return self._error_result(
                conversation_id,
                "Hermes bridge error. Please check the logs.",
            )

        response_text = data.get("response", "")
        if not response_text:
            response_text = "Hermes returned an empty response."

        response = intent.IntentResponse(language=language)
        response.async_set_speech(response_text)

        return conversation.ConversationResult(
            conversation_id=data.get("conversation_id", conversation_id),
            response=response,
        )

    def _error_result(
        self, conversation_id: str, text: str
    ) -> conversation.ConversationResult:
        """Build a conversation result with an error message."""
        response = intent.IntentResponse(language="en")
        response.async_set_speech(text)
        return conversation.ConversationResult(
            conversation_id=conversation_id,
            response=response,
        )
