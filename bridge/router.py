"""Conversation request routing logic."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bridge.config import BridgeConfig
from bridge.hermes_runner import HermesExecutionError, HermesRunner
from bridge.models import ConversationRequest, ConversationResponse
from bridge.session_store import ConversationSession, SessionStore

_LOGGER = logging.getLogger(__name__)


class Router:
    """Routes HA conversation requests to Hermes (and eventually local agents)."""

    def __init__(self, config: BridgeConfig, store: SessionStore) -> None:
        """Initialize router."""
        self.config = config
        self.store = store
        self.runner = HermesRunner(
            hermes_bin=config.hermes_bin,
            profile=config.profile,
            timeout=config.timeout,
        )

    def _build_prompt(self, request: ConversationRequest) -> str:
        lines = [
            "You are handling a Home Assistant Assist request through the Hermes bridge.",
            "",
            f"User: {request.user_name or 'unknown'}",
            f"Language: {request.language}",
            f"Device ID: {request.device_id or 'unknown'}",
            f"Home Assistant conversation_id: {request.conversation_id}",
            "",
            "Instructions:",
            "- Respond in the user's language.",
            "- Keep answers concise and voice-friendly.",
            "- If the user is asking to control Home Assistant devices, use available tools when appropriate.",
            "- If the task is ambiguous, prefer a short clarifying question.",
            "",
            "User request:",
            request.text,
        ]
        return "\n".join(lines)

    async def handle(self, request: ConversationRequest) -> ConversationResponse:
        """Handle a conversation request."""
        if self.config.routing_mode != "hermes_only":
            _LOGGER.warning(
                "Routing mode '%s' is not implemented in MVP; falling back to hermes_only",
                self.config.routing_mode,
            )

        prompt = self._build_prompt(request)
        existing = self.store.lookup(request.conversation_id)
        resume_session_id = existing.hermes_session_id if existing else None

        try:
            result = await self.runner.run(prompt, resume_session_id)
        except HermesExecutionError as err:
            # If resume failed, start a fresh session transparently.
            if resume_session_id and "resume" in str(err).lower():
                _LOGGER.warning(
                    "Hermes resume failed for session %s, starting fresh", resume_session_id
                )
                result = await self.runner.run(prompt, None)
            else:
                raise

        now = datetime.now(timezone.utc)
        session_id = result.session_id
        if not session_id:
            # If Hermes did not report a session_id, reuse existing or record fallback.
            session_id = resume_session_id or "unknown"

        self.store.upsert(
            ConversationSession(
                ha_conversation_id=request.conversation_id,
                hermes_session_id=session_id,
                user_id=request.user_id,
                user_name=request.user_name,
                device_id=request.device_id,
                last_seen_at=now,
                created_at=existing.created_at if existing else now,
            )
        )

        return ConversationResponse(
            response=result.stdout.strip(),
            conversation_id=request.conversation_id,
            handled_by="hermes",
            session_id=session_id,
        )
