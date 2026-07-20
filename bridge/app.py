"""FastAPI application for the Hermes bridge."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from auth import verify_token
from config import BridgeConfig
from models import (
    ConversationRequest,
    ConversationResponse,
    HealthResponse,
    InfoResponse,
)
from router import Router
from session_store import SessionStore

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bootstrap config and session store."""
    config = BridgeConfig.from_env()
    store = SessionStore(config.db_path)
    _LOGGER.info(
        "Bridge starting with profile=%s routing_mode=%s",
        config.profile,
        config.routing_mode,
    )
    app.state.config = config
    app.state.store = store
    yield
    _LOGGER.info("Bridge shutting down")


app = FastAPI(title="Hermes HA Bridge", version="0.1.0", lifespan=lifespan)


async def get_router(request: Request) -> Router:
    """Create a Router from app state."""
    return Router(config=request.app.state.config, store=request.app.state.store)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check."""
    return HealthResponse(status="ok")


@app.get("/api/info", response_model=InfoResponse)
async def info(
    token: Annotated[str, Depends(verify_token)],
    request: Request,
) -> InfoResponse:
    """Return bridge metadata."""
    config: BridgeConfig = request.app.state.config
    return InfoResponse(
        version="0.1.0",
        routing_mode=config.routing_mode,
        profile=config.profile,
    )


@app.post("/api/conversation", response_model=ConversationResponse)
async def conversation(
    payload: ConversationRequest,
    token: Annotated[str, Depends(verify_token)],
    router: Annotated[Router, Depends(get_router)],
) -> ConversationResponse:
    """Receive HA conversation request and return Hermes response."""
    return await router.handle(payload)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return JSON error responses for unhandled exceptions."""
    _LOGGER.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal bridge error"},
    )


if __name__ == "__main__":
    import uvicorn

    config = BridgeConfig.from_env()
    uvicorn.run(
        "app:app",
        host=config.host,
        port=config.port,
        log_level="info",
        reload=False,
    )
