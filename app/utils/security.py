"""Shared API authentication helpers."""

import secrets

import logfire
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

security_scheme = HTTPBearer(auto_error=False)


def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> str | None:
    """Validate the backend bearer token without exposing it to browser clients."""
    if not settings.API_KEY:
        return None

    supplied_key = credentials.credentials if credentials else ""
    if not secrets.compare_digest(supplied_key, settings.API_KEY):
        logfire.warning("Unauthorized request: invalid or missing API key.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return supplied_key
