"""Conversation request routing logic."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from time import perf_counter
from datetime import datetime, timezone

import httpx
import websockets

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
            provider=config.hermes_provider,
            model=config.hermes_model,
            toolsets=config.hermes_toolsets,
            timeout=config.timeout,
        )
        self.smart_runner = HermesRunner(
            hermes_bin=config.hermes_bin,
            profile=config.profile,
            toolsets=config.hermes_toolsets,
            timeout=config.timeout,
        )

    def _normalize_local_command(self, text: str) -> str | None:
        """Normalize rough German smart-home phrasing into something HA parses better."""
        t = " ".join(text.strip().lower().split())
        has_light = bool(re.search(r"\blicht\b|\blampe\b", t))
        has_room = bool(re.search(r"\b(im|in der|in dem|im\s+|in\s+)\b", t)) or "wohnzimmer" in t
        if has_light and has_room:
            if re.search(r"\baus\b|\bausschalten\b", t):
                room = re.sub(r".*\b(?:im|in der|in dem)\s+", "", t)
                room = re.sub(r"\b(?:ausschalten|aus)\b.*", "", room).strip()
                if room:
                    return f"Schalte das Licht im {room} aus"
            if re.search(r"\ban\b|\beinschalten\b|\banschalten\b", t):
                room = re.sub(r".*\b(?:im|in der|in dem)\s+", "", t)
                room = re.sub(r"\b(?:einschalten|anschalten|an)\b.*", "", room).strip()
                if room:
                    return f"Schalte das Licht im {room} an"
        return None

    def _append_trace(self, trace: dict) -> None:
        """Append a JSONL trace entry for debugging voice requests end-to-end."""
        trace_path = self.config.trace_path
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        with trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")

    def _is_fast_home_assistant_candidate(self, text: str) -> bool:
        """Heuristic: simple direct device control/status should stay local and fast."""
        t = text.strip().lower()
        if len(t) > 120:
            return False

        fast_patterns = [
            r"\blicht\b",
            r"\blampe\b",
            r"\bschalte\b",
            r"\bmach\b",
            r"\ban\b",
            r"\baus\b",
            r"\brollladen\b|\brollo\b|\bjalousie\b",
            r"\bheizung\b|\bthermostat\b|\btemperatur\b",
            r"\bfenster\b|\btür\b|\boffen\b|\bgeschlossen\b",
            r"\bsteckdose\b|\bszene\b|\bklima\b|\blüfter\b",
            r"\bwie warm\b|\bist .* an\b|\bstatus\b",
        ]
        return any(re.search(pattern, t) for pattern in fast_patterns)

    def _should_try_home_assistant_local(self, text: str) -> bool:
        """Decide whether HA's built-in local agent should get first shot."""
        if self.config.routing_mode == "cascade":
            return True
        return self.config.routing_mode == "local_first" and self._is_fast_home_assistant_candidate(text)

    def _looks_like_explicit_answer_failure(self, response_text: str) -> bool:
        """Detect answers that explicitly failed so we should continue to the next agent."""
        resp = response_text.strip().lower()
        if not resp:
            return True
        failure_markers = [
            "ich weiß nicht",
            "ich weiss nicht",
            "ich bin mir nicht sicher",
            "entschuldigung, ich",
            "kann ich nicht",
            "konnte ich nicht",
            "das habe ich nicht verstanden",
            "i don't know",
            "i do not know",
            "i'm not sure",
            "sorry, i",
        ]
        return any(marker in resp for marker in failure_markers)

    async def _try_home_assistant_local(self, request: ConversationRequest) -> ConversationResponse | None:
        """Send obvious home-control commands to HA's native conversation agent first."""
        if not (self.config.ha_url and self.config.ha_token):
            return None

        request_text = request.text
        payload = {
            "text": request_text,
            "language": request.language,
            "conversation_id": request.conversation_id,
            "agent_id": "conversation.home_assistant",
        }
        headers = {
            "Authorization": f"Bearer {self.config.ha_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.config.ha_url}/api/conversation/process",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()
        except Exception as err:
            _LOGGER.warning("Local HA fast-path failed: %s", err)
            return None

        response = body.get("response", {})
        response_type = response.get("response_type")
        speech = (
            response.get("speech", {})
            .get("plain", {})
            .get("speech", "")
            .strip()
        )
        if response_type == "error" or not speech:
            normalized = self._normalize_local_command(request.text)
            if normalized and normalized != request_text:
                payload["text"] = normalized
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            f"{self.config.ha_url}/api/conversation/process",
                            headers=headers,
                            json=payload,
                        )
                        resp.raise_for_status()
                        body = resp.json()
                except Exception as err:
                    _LOGGER.warning("Normalized local HA fast-path failed: %s", err)
                    return None

                response = body.get("response", {})
                response_type = response.get("response_type")
                speech = (
                    response.get("speech", {})
                    .get("plain", {})
                    .get("speech", "")
                    .strip()
                )
                if response_type == "error" or not speech:
                    return None
            else:
                return None

        return ConversationResponse(
            response=speech,
            conversation_id=body.get("conversation_id") or request.conversation_id,
            handled_by="home_assistant_local",
            session_id=None,
        )

    async def _try_home_assistant_ai(self, request: ConversationRequest) -> ConversationResponse | None:
        """Use a fast HA-hosted AI provider before falling through to full Hermes."""
        if not (self.config.ha_url and self.config.ha_token and self.config.ha_ai_provider):
            return None

        ws_url = (
            self.config.ha_url.replace("http://", "ws://").replace("https://", "wss://")
            + "/api/websocket"
        )
        provider = self.config.ha_ai_provider

        try:
            async with websockets.connect(ws_url, max_size=2_000_000) as ws:
                await ws.recv()
                await ws.send(
                    json.dumps({"type": "auth", "access_token": self.config.ha_token})
                )
                auth_msg = json.loads(await ws.recv())
                if auth_msg.get("type") != "auth_ok":
                    return None

                await ws.send(
                    json.dumps(
                        {
                            "id": 1,
                            "type": "subscribe_events",
                            "event_type": "ai_agent_ha_response",
                        }
                    )
                )
                sub_msg = json.loads(await ws.recv())
                if not sub_msg.get("success", False):
                    return None

                await ws.send(
                    json.dumps(
                        {
                            "id": 2,
                            "type": "call_service",
                            "domain": "ai_agent_ha",
                            "service": "query",
                            "service_data": {
                                "provider": provider,
                                "prompt": request.text,
                                "debug": False,
                            },
                        }
                    )
                )

                pending_event: dict | None = None
                service_ack = False
                deadline = perf_counter() + self.config.ha_ai_timeout
                while perf_counter() < deadline:
                    timeout = max(0.1, deadline - perf_counter())
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                    if msg.get("type") == "result" and msg.get("id") == 2:
                        if not msg.get("success", False):
                            return None
                        service_ack = True
                        if pending_event is None:
                            continue
                        data = pending_event
                    elif (
                        msg.get("type") == "event"
                        and msg.get("event", {}).get("event_type") == "ai_agent_ha_response"
                    ):
                        data = msg.get("event", {}).get("data", {})
                        if not service_ack:
                            pending_event = data
                            continue
                    else:
                        continue

                    answer = data.get("answer", "").strip()
                    if data.get("success") and answer and not self._looks_like_explicit_answer_failure(answer):
                        return ConversationResponse(
                            response=answer,
                            conversation_id=request.conversation_id,
                            handled_by=f"ha_ai_{provider}",
                            session_id=None,
                        )
                    return None
        except Exception as err:
            _LOGGER.warning("HA AI fast-path failed: %s", err)
            return None

        return None

    def _looks_like_clarifying_failure(self, request_text: str, response_text: str) -> bool:
        """Detect low-confidence first-pass answers worth escalating to a smarter model."""
        req = request_text.strip().lower()
        resp = response_text.strip().lower()
        if len(req) > 80:
            return False
        markers = [
            "was genau",
            "welches gerät",
            "welchen raum",
            "bitte sag kurz",
            "kannst du präzisieren",
            "was meinst du genau",
        ]
        if any(marker in resp for marker in markers):
            return True
        return "?" in resp and len(resp) <= 80

    def _looks_like_fast_agent_failure(self, request_text: str, response_text: str) -> bool:
        """Detect weak fast-model answers that should fall through to full Hermes."""
        if self._looks_like_clarifying_failure(request_text, response_text):
            return True
        return self._looks_like_explicit_answer_failure(response_text)

    def _fast_local_clarification(self, text: str) -> str | None:
        """Return an immediate German clarification for short failed home-control commands."""
        t = text.strip().lower()
        if len(t) > 80:
            return None
        if re.search(r"\blicht\b|\blampe\b", t):
            return "Welches Licht oder welcher Raum?"
        if re.search(r"\brollladen\b|\brollo\b|\bjalousie\b", t):
            return "Welcher Rollladen oder welcher Raum?"
        if re.search(r"\bheizung\b|\bthermostat\b|\btemperatur\b", t):
            return "Welcher Raum oder welches Thermostat?"
        if re.search(r"\bsteckdose\b|\bklima\b|\blüfter\b|\bfenster\b|\btür\b", t):
            return "Welches Gerät oder welcher Raum?"
        if re.search(r"\ban\b|\baus\b|\bein\b|\bausschalten\b|\beinschalten\b|\bschalte\b|\bmach\b", t):
            return "Welches Gerät oder welcher Raum?"
        return None

    def _fast_canned_response(self, text: str) -> str | None:
        """Return instant responses for common voice prompts that don't need a full model call."""
        t = " ".join(text.strip().lower().split())
        if re.search(r"\bwas kannst du\b|\bund das kannst du alles\b|\bwas kannst du alles\b", t):
            return "Ich kann dein Smart Home steuern, Zustände prüfen und kurze Fragen beantworten."
        return None

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
        started = perf_counter()
        canned = self._fast_canned_response(request.text)
        if canned is not None:
            now = datetime.now(timezone.utc)
            response = ConversationResponse(
                response=canned,
                conversation_id=request.conversation_id,
                handled_by="fast_canned",
                session_id=None,
            )
            self._append_trace(
                {
                    "timestamp": now.isoformat(),
                    "latency_seconds": round(perf_counter() - started, 3),
                    "ha_conversation_id": request.conversation_id,
                    "route": "fast_canned",
                    "request_text": request.text,
                    "hermes_response_text": None,
                    "tts_input_text": response.response,
                    "metadata": request.metadata,
                }
            )
            return response

        attempted_local = False
        if self._should_try_home_assistant_local(request.text):
            attempted_local = True
            local_result = await self._try_home_assistant_local(request)
            if local_result is not None:
                now = datetime.now(timezone.utc)
                self._append_trace(
                    {
                        "timestamp": now.isoformat(),
                        "latency_seconds": round(perf_counter() - started, 3),
                        "ha_conversation_id": request.conversation_id,
                        "route": "home_assistant_local",
                        "request_text": request.text,
                        "hermes_response_text": None,
                        "tts_input_text": local_result.response,
                        "metadata": request.metadata,
                    }
                )
                return local_result

            fast_clarification = self._fast_local_clarification(request.text)
            if self.config.routing_mode == "local_first" and fast_clarification is not None:
                now = datetime.now(timezone.utc)
                response = ConversationResponse(
                    response=fast_clarification,
                    conversation_id=request.conversation_id,
                    handled_by="fast_clarification",
                    session_id=None,
                )
                self._append_trace(
                    {
                        "timestamp": now.isoformat(),
                        "latency_seconds": round(perf_counter() - started, 3),
                        "ha_conversation_id": request.conversation_id,
                        "route": "fast_clarification",
                        "request_text": request.text,
                        "hermes_response_text": None,
                        "tts_input_text": response.response,
                        "metadata": request.metadata,
                    }
                )
                return response

        if self.config.routing_mode not in {"hermes_only", "local_first", "cascade"}:
            _LOGGER.warning(
                "Routing mode '%s' is not implemented in MVP; falling back to hermes_only",
                self.config.routing_mode,
            )

        prompt = self._build_prompt(request)
        existing = self.store.lookup(request.conversation_id)
        resume_session_id = existing.hermes_session_id if existing else None

        route_label = "hermes"
        used_smart_runner = False
        if self.config.routing_mode == "cascade":
            ai_result = await self._try_home_assistant_ai(request)
            if ai_result is not None:
                now = datetime.now(timezone.utc)
                self._append_trace(
                    {
                        "timestamp": now.isoformat(),
                        "latency_seconds": round(perf_counter() - started, 3),
                        "ha_conversation_id": request.conversation_id,
                        "route": ai_result.handled_by,
                        "request_text": request.text,
                        "hermes_response_text": None,
                        "tts_input_text": ai_result.response,
                        "metadata": request.metadata,
                    }
                )
                return ai_result

        active_runner = self.smart_runner if self.config.routing_mode == "cascade" else self.runner
        try:
            result = await active_runner.run(prompt, resume_session_id)
        except HermesExecutionError as err:
            # If resume failed, start a fresh session transparently.
            if resume_session_id and "resume" in str(err).lower():
                _LOGGER.warning(
                    "Hermes resume failed for session %s, starting fresh", resume_session_id
                )
                result = await active_runner.run(prompt, None)
            elif self.config.routing_mode == "cascade":
                _LOGGER.warning(
                    "HA AI fast path failed (%s); escalating to full Hermes",
                    err,
                )
                result = await self.smart_runner.run(prompt, resume_session_id)
                used_smart_runner = True
            else:
                raise

        if self.config.routing_mode == "cascade":
            route_label = "hermes_smart"
        elif attempted_local and self._looks_like_clarifying_failure(request.text, result.stdout.strip()):
            _LOGGER.info("Escalating ambiguous fast-path request to smarter Hermes model")
            result = await self.smart_runner.run(prompt, resume_session_id)
            used_smart_runner = True

        if self.config.routing_mode == "cascade":
            route_label = "hermes_smart"

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

        response_text = result.stdout.strip()
        self._append_trace(
            {
                "timestamp": now.isoformat(),
                "latency_seconds": round(perf_counter() - started, 3),
                "ha_conversation_id": request.conversation_id,
                "hermes_session_id": session_id,
                "resume_session_id": resume_session_id,
                "route": route_label,
                "user_name": request.user_name,
                "user_id": request.user_id,
                "device_id": request.device_id,
                "language": request.language,
                "request_text": request.text,
                "prompt_sent_to_hermes": prompt,
                "hermes_response_text": response_text,
                "tts_input_text": response_text,
                "usage": result.usage,
                "metadata": request.metadata,
            }
        )

        return ConversationResponse(
            response=response_text,
            conversation_id=request.conversation_id,
            handled_by=route_label,
            session_id=session_id,
        )
