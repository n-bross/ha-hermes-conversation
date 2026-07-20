"""SQLite-backed HA conversation to Hermes session map."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ConversationSession:
    ha_conversation_id: str
    hermes_session_id: str
    user_id: str | None
    user_name: str | None
    device_id: str | None
    last_seen_at: datetime
    created_at: datetime


class SessionStore:
    """Persistent mapping between HA conversation IDs and Hermes session IDs."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS conversation_sessions (
        ha_conversation_id TEXT PRIMARY KEY,
        hermes_session_id TEXT NOT NULL,
        user_id TEXT,
        user_name TEXT,
        device_id TEXT,
        last_seen_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_last_seen ON conversation_sessions(last_seen_at);
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize store and create schema."""
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(self.SCHEMA)
            conn.commit()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _iso(self, dt: datetime) -> str:
        return dt.isoformat()

    def _parse(self, value: str) -> datetime:
        return datetime.fromisoformat(value)

    def lookup(self, ha_conversation_id: str) -> ConversationSession | None:
        """Find a stored session by HA conversation ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_sessions WHERE ha_conversation_id = ?",
                (ha_conversation_id,),
            ).fetchone()

        if not row:
            return None

        return ConversationSession(
            ha_conversation_id=row["ha_conversation_id"],
            hermes_session_id=row["hermes_session_id"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            device_id=row["device_id"],
            last_seen_at=self._parse(row["last_seen_at"]),
            created_at=self._parse(row["created_at"]),
        )

    def upsert(self, mapping: ConversationSession) -> None:
        """Create or update a mapping."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_sessions
                (ha_conversation_id, hermes_session_id, user_id, user_name,
                 device_id, last_seen_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ha_conversation_id) DO UPDATE SET
                    hermes_session_id = excluded.hermes_session_id,
                    user_id = excluded.user_id,
                    user_name = excluded.user_name,
                    device_id = excluded.device_id,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    mapping.ha_conversation_id,
                    mapping.hermes_session_id,
                    mapping.user_id,
                    mapping.user_name,
                    mapping.device_id,
                    self._iso(mapping.last_seen_at),
                    self._iso(mapping.created_at),
                ),
            )
            conn.commit()

    def delete_stale(self, ttl_seconds: float = 86400.0) -> int:
        """Delete mappings older than ttl_seconds. Returns rows deleted."""
        cutoff = self._now() - timedelta(seconds=ttl_seconds)
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM conversation_sessions WHERE last_seen_at < ?",
                (self._iso(cutoff),),
            )
            conn.commit()
            return cur.rowcount

    def delete(self, ha_conversation_id: str) -> bool:
        """Delete a mapping by HA conversation ID."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM conversation_sessions WHERE ha_conversation_id = ?",
                (ha_conversation_id,),
            )
            conn.commit()
            return cur.rowcount > 0
