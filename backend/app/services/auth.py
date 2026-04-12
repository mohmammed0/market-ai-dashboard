"""Authentication service — JWT-based API authentication.

Provides token creation, verification, and a FastAPI dependency for
protecting routes. Uses HMAC-SHA256 for password hashing.

Security notes:
- Change AUTH_SECRET_KEY in production (use: openssl rand -hex 32)
- Set a strong AUTH_DEFAULT_PASSWORD via env var
- Tokens expire after AUTH_ACCESS_TOKEN_EXPIRE_MINUTES (default 24h)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.config import (
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES,
    AUTH_ALGORITHM,
    AUTH_DEFAULT_PASSWORD,
    AUTH_DEFAULT_USERNAME,
    AUTH_ENABLED,
    AUTH_SECRET_KEY,
)
from backend.app.core.logging_utils import get_logger

logger = get_logger(__name__)

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None

security = HTTPBearer(auto_error=False)


def _hash_password(password: str) -> str:
    """Simple HMAC-SHA256 hash (no external bcrypt dependency needed)."""
    return hmac.new(
        AUTH_SECRET_KEY.encode(), password.encode(), hashlib.sha256
    ).hexdigest()


def _verify_password(plain: str, hashed: str) -> bool:
    return hmac.compare_digest(_hash_password(plain), hashed)


# In-memory user store (single-user for now, extensible)
_users: dict[str, dict] = {}


def _ensure_default_user() -> None:
    """Create default admin user if none exists."""
    if AUTH_DEFAULT_USERNAME and AUTH_DEFAULT_USERNAME not in _users:
        password = AUTH_DEFAULT_PASSWORD or secrets.token_urlsafe(16)
        _users[AUTH_DEFAULT_USERNAME] = {
            "username": AUTH_DEFAULT_USERNAME,
            "password_hash": _hash_password(password),
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if not AUTH_DEFAULT_PASSWORD:
            logger.warning(
                "No AUTH_DEFAULT_PASSWORD set. Generated temporary password: %s "
                "— set MARKET_AI_AUTH_DEFAULT_PASSWORD env var for persistence.",
                password,
            )
        else:
            logger.info("Default auth user '%s' initialized.", AUTH_DEFAULT_USERNAME)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Verify credentials. Returns user dict or None."""
    _ensure_default_user()
    user = _users.get(username)
    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    return user


def create_access_token(username: str, role: str = "admin") -> str:
    """Create a JWT access token."""
    if pyjwt is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PyJWT not installed. Run: pip install PyJWT",
        )
    expire = datetime.now(timezone.utc) + timedelta(minutes=AUTH_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return pyjwt.encode(payload, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    if pyjwt is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PyJWT not installed.",
        )
    try:
        return pyjwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """FastAPI dependency — extracts and validates the JWT bearer token."""
    if not AUTH_ENABLED:
        return {"username": "anonymous", "role": "admin"}

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Send Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    _ensure_default_user()
    user = _users.get(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return {"username": username, "role": payload.get("role", "user")}


def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Lenient auth dependency — returns None if no token, doesn't block."""
    if not AUTH_ENABLED or credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        return {"username": payload.get("sub"), "role": payload.get("role", "user")}
    except Exception:
        return None
