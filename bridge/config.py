"""Bridge configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BridgeConfig:
    """Bridge runtime configuration."""

    token: str
    profile: str
    hermes_bin: str
    hermes_provider: str | None
    hermes_model: str | None
    hermes_toolsets: str | None
    ha_url: str | None
    ha_token: str | None
    ha_ai_provider: str | None
    ha_ai_timeout: float
    timeout: float
    routing_mode: str
    data_dir: Path
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        """Load configuration from environment variables."""
        data_dir = Path(os.environ.get("HERMES_DATA_DIR", "data"))
        data_dir.mkdir(parents=True, exist_ok=True)

        return cls(
            token=os.environ.get("HERMES_BRIDGE_TOKEN", ""),
            profile=os.environ.get("HERMES_PROFILE", "default"),
            hermes_bin=os.environ.get("HERMES_BIN", "hermes"),
            hermes_provider=os.environ.get("HERMES_PROVIDER") or None,
            hermes_model=os.environ.get("HERMES_MODEL") or None,
            hermes_toolsets=os.environ.get("HERMES_TOOLSETS") or None,
            ha_url=os.environ.get("HASS_URL") or os.environ.get("HA_URL") or None,
            ha_token=os.environ.get("HASS_TOKEN") or os.environ.get("HA_TOKEN") or None,
            ha_ai_provider=os.environ.get("HASS_AI_PROVIDER") or os.environ.get("HA_AI_PROVIDER") or None,
            ha_ai_timeout=float(os.environ.get("HASS_AI_TIMEOUT", os.environ.get("HA_AI_TIMEOUT", "12"))),
            timeout=float(os.environ.get("HERMES_TIMEOUT", "30")),
            routing_mode=os.environ.get("HERMES_ROUTING_MODE", "hermes_only"),
            data_dir=data_dir,
            host=os.environ.get("HERMES_BRIDGE_HOST", "127.0.0.1"),
            port=int(os.environ.get("HERMES_BRIDGE_PORT", "8787")),
        )

    @property
    def db_path(self) -> Path:
        """Path to SQLite session store."""
        return self.data_dir / "session_map.sqlite3"

    @property
    def trace_path(self) -> Path:
        """Path to JSONL trace log for end-to-end voice debugging."""
        return self.data_dir / "conversation_traces.jsonl"
