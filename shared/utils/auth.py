"""Bearer auth utilities for API routes."""

from __future__ import annotations

from fastapi import Header, HTTPException, status


def require_bearer(expected_token: str, authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    provided = authorization.split(" ", 1)[1].strip()
    if provided != expected_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")


def bearer_header(authorization: str | None = Header(default=None)) -> str | None:
    return authorization
