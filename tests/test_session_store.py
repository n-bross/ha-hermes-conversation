import pytest
from datetime import datetime, timezone
from bridge.session_store import SessionStore, ConversationSession

def test_upsert_and_lookup(tmp_path):
    db = tmp_path / "s.sqlite3"
    store = SessionStore(db)
    sess = ConversationSession(
        ha_conversation_id="ha1",
        hermes_session_id="hermes-abc",
        user_id="u1",
        user_name="Nico",
        device_id=None,
        last_seen_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    store.upsert(sess)
    found = store.lookup("ha1")
    assert found is not None
    assert found.hermes_session_id == "hermes-abc"

def test_delete_stale(tmp_path):
    db = tmp_path / "s2.sqlite3"
    store = SessionStore(db)
    old = ConversationSession(
        ha_conversation_id="ha_old",
        hermes_session_id="s_old",
        user_id=None, user_name=None, device_id=None,
        last_seen_at=datetime(2020,1,1, tzinfo=timezone.utc),
        created_at=datetime(2020,1,1, tzinfo=timezone.utc),
    )
    store.upsert(old)
    deleted = store.delete_stale(ttl_seconds=3600)
    assert deleted >= 1
    assert store.lookup("ha_old") is None
