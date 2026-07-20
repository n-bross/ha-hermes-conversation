"""Client for the Hermes bridge HTTP API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .const import BRIDGE_CONVERSATION_PATH, HEALTH_PATH, MAX_TEXT_LENGTH

_LOGGER = logging.getLogger(__name__)


class HermesBridgeError(Exception):
    """Base bridge error."""


class HermesBridgeAuthError(HermesBridgeError):
    """Authentication failed."""


class HermesBridgeTimeout(HermesBridgeError):
    """Bridge request timed out."""


class HermesBridgeUnavailable(HermesBridgeError):
    """Bridge is unreachable."""


class HermesBridgeClient:
    """Async client that talks to the Hermes bridge."""

    def __init__(self, bridge_url: str, token: str, timeout: float = 30) -> None:
        """Initialize client."""
        self.bridge_url = bridge_url.rstrip("/")
        self.token = token
        self.timeout = float(timeout)
        self._client = httpx.AsyncClient(timeout=self.timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def health_check(self) -> dict[str, Any]:
        """Call bridge /health endpoint."""
        url = f"{self.bridge_url}{HEALTH_PATH}"
        try:
            response = await self._client.get(url, headers=self._headers())
        except httpx.TimeoutException as err:
            raise HermesBridgeTimeout(f"Health check timed out: {err}") from err
        except httpx.TransportError as err:
            raise HermesBridgeUnavailable(f"Bridge unavailable: {err}") from err

        if response.status_code == 401:
            raise HermesBridgeAuthError("Invalid bridge token")
        response.raise_for_status()
        return response.json()

    async def send_request(
        self,
        text: str,
        conversation_id: str,
        language: str,
        user_name: str | None = None,
        user_id: str | None = None,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a conversation request to the bridge."""
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH]

        payload = {
            "text": text,
            "conversation_id": conversation_id,
            "language": language,
            "user_name": user_name,
            "user_id": user_id,
            "device_id": device_id,
            "agent_id": "hermes",
            "metadata": {"source": "assist", "ha_agent": "hermes_conversation"},
        }

        url = f"{self.bridge_url}{BRIDGE_CONVERSATION_PATH}"
        try:
            response = await self._client.post(
                url, json=payload, headers=self._headers(), timeout=self.timeout
            )
        except httpx.TimeoutException as err:
            raise HermesBridgeTimeout(f"Request timed out: {err}") from err
        except httpx.TransportError as err:
            raise HermesBridgeUnavailable(f"Bridge unavailable: {err}") from err

        if response.status_code == 401:
            raise HermesBridgeAuthError("Invalid bridge token")
        if response.status_code >= 500:
            raise HermesBridgeError(f"Bridge server error: {response.status_code}")

        try:
            data = response.json()
        except ValueError as err:
            raise HermesBridgeError(f"Invalid JSON from bridge: {err}") from err

        return data

    async def async_close(self) -> None:
        """Close underlying client."""
        await self._client.aclose()
