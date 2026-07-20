"""Pydantic models for bridge requests and responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConversationRequest(BaseModel):
    """Incoming request from Home Assistant."""

    text: str = Field(..., min_length=1)
    conversation_id: str = Field(..., min_length=1)
    language: str = "en"
    user_name: str | None = None
    user_id: str | None = None
    device_id: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] | None = None


class ConversationResponse(BaseModel):
    """Outgoing response to Home Assistant."""

    response: str
    conversation_id: str
    handled_by: str = "hermes"
    session_id: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"


class InfoResponse(BaseModel):
    """Bridge info response."""

    version: str
    routing_mode: str
    profile: str
