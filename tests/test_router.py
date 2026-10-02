import pytest
from unittest.mock import AsyncMock, patch

from bridge.config import BridgeConfig
from bridge.models import ConversationRequest, ConversationResponse
from bridge.router import Router
from bridge.session_store import SessionStore


class FakeResult:
    def __init__(self, stdout: str, session_id: str = "s1", usage: dict | None = None):
        self.stdout = stdout
        self.session_id = session_id
        self.usage = usage or {}


@pytest.mark.asyncio
async def test_router_falls_back_on_resume_error(tmp_path):
    cfg = BridgeConfig(
        token="t",
        profile="default",
        hermes_bin="hermes",
        hermes_provider=None,
        hermes_model=None,
        hermes_toolsets=None,
        ha_url=None,
        ha_token=None,
        ha_ai_provider=None,
        ha_ai_timeout=12,
        timeout=5,
        routing_mode="hermes_only",
        data_dir=tmp_path,
        host="127.0.0.1",
        port=0,
    )
    store = SessionStore(tmp_path / "db.sqlite3")
    router = Router(cfg, store)
    req = ConversationRequest(text="hi", conversation_id="c1")

    prompt = router._build_prompt(req)
    assert "User request" in prompt


@pytest.mark.asyncio
async def test_cascade_uses_ha_ai_after_local_miss(tmp_path):
    cfg = BridgeConfig(
        token="t",
        profile="default",
        hermes_bin="hermes",
        hermes_provider=None,
        hermes_model=None,
        hermes_toolsets=None,
        ha_url="http://ha.local",
        ha_token="token",
        ha_ai_provider="openrouter",
        ha_ai_timeout=12,
        timeout=5,
        routing_mode="cascade",
        data_dir=tmp_path,
        host="127.0.0.1",
        port=0,
    )
    store = SessionStore(tmp_path / "db.sqlite3")
    router = Router(cfg, store)
    req = ConversationRequest(text="Warum ist der Himmel blau?", conversation_id="c1", language="de")

    ai_response = ConversationResponse(
        response="Kurze Antwort",
        conversation_id="c1",
        handled_by="ha_ai_openrouter",
        session_id=None,
    )

    with patch.object(router, "_try_home_assistant_local", AsyncMock(return_value=None)) as local_mock, \
         patch.object(router, "_try_home_assistant_ai", AsyncMock(return_value=ai_response)) as ai_mock, \
         patch.object(router.smart_runner, "run", AsyncMock()) as smart_mock:
        response = await router.handle(req)

    local_mock.assert_awaited_once()
    ai_mock.assert_awaited_once()
    smart_mock.assert_not_called()
    assert response == ai_response


@pytest.mark.asyncio
async def test_cascade_falls_through_to_full_hermes_when_ha_ai_misses(tmp_path):
    cfg = BridgeConfig(
        token="t",
        profile="default",
        hermes_bin="hermes",
        hermes_provider=None,
        hermes_model=None,
        hermes_toolsets=None,
        ha_url="http://ha.local",
        ha_token="token",
        ha_ai_provider="openrouter",
        ha_ai_timeout=12,
        timeout=5,
        routing_mode="cascade",
        data_dir=tmp_path,
        host="127.0.0.1",
        port=0,
    )
    store = SessionStore(tmp_path / "db.sqlite3")
    router = Router(cfg, store)
    req = ConversationRequest(text="Erzähl mir etwas Komplexes", conversation_id="c2", language="de")

    with patch.object(router, "_try_home_assistant_local", AsyncMock(return_value=None)) as local_mock, \
         patch.object(router, "_try_home_assistant_ai", AsyncMock(return_value=None)) as ai_mock, \
         patch.object(router.smart_runner, "run", AsyncMock(return_value=FakeResult("Hermes Antwort", "smart2"))) as smart_mock:
        response = await router.handle(req)

    local_mock.assert_awaited_once()
    ai_mock.assert_awaited_once()
    smart_mock.assert_awaited_once()
    assert response == ConversationResponse(
        response="Hermes Antwort",
        conversation_id="c2",
        handled_by="hermes_smart",
        session_id="smart2",
    )
