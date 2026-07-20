"""Authentication for the Hermes bridge."""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_LOGGER = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    """Verify the bearer token matches the configured bridge token."""
    token = os.environ.get("HERMES_BRIDGE_TOKEN", "")
    if not token:
        _LOGGER.error("HERMES_BRIDGE_TOKEN is not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bridge token not configured",
        )

    if credentials is None or credentials.credentials != token:
        _LOGGER.warning("Invalid or missing bearer token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials
