"""Authentication service — JWT-based API authentication.

Provides token creation, verification, and FastAPI dependencies for
protecting routes.

Security notes:
- Production requires an explicit password and a non-default JWT secret.
- Passwords are hashed with PBKDF2-HMAC-SHA256 and a per-user random salt.
- Legacy HMAC-only hashes are still accepted for compatibility and upgraded
  in-memory on successful authentication.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.config import (
    APP_ENV,
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES,
    AUTH_ALGORITHM,
    AUTH_DEFAULT_PASSWORD,
    AUTH_DEFAULT_USERNAME,
    AUTH_ENABLED,
    AUTH_SECRET_KEY,
    AUTH_SECRET_KEY_IS_DEFAULT,
)
from backend.app.core.logging_utils import get_logger

logger = get_logger(__name__)

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None

security = HTTPBearer(auto_error=False)

_PBKDF2_PREFIX = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 390000

_RUNTIME_USERNAME_KEY = "auth.default_username"
_RUNTIME_PASSWORD_HASH_KEY = "auth.default_password_hash"


def _legacy_hash_password(password: str) -> str:
    return hmac.new(AUTH_SECRET_KEY.encode(), password.encode(), hashlib.sha256).hexdigest()


def _hash_password(password: str, *, salt: str | None = None, iterations: int = _PBKDF2_ITERATIONS) -> str:
    resolved_salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        resolved_salt.encode("utf-8"),
        int(iterations),
    )
    return f"{_PBKDF2_PREFIX}${int(iterations)}${resolved_salt}${derived.hex()}"


def _verify_password(plain: str, hashed: str) -> bool:
    if str(hashed or "").startswith(f"{_PBKDF2_PREFIX}$"):
        try:
            _, iterations, salt, digest = hashed.split("$", 3)
            candidate = _hash_password(plain, salt=salt, iterations=int(iterations))
            return hmac.compare_digest(candidate, hashed)
        except Exception:
            return False
    return hmac.compare_digest(_legacy_hash_password(plain), hashed)


def _get_runtime_default_username() -> str:
    try:
        from backend.app.services.runtime_settings import get_runtime_setting_value

        username = get_runtime_setting_value(_RUNTIME_USERNAME_KEY)
        return str(username or "").strip()
    except Exception:
        return AUTH_DEFAULT_USERNAME


def _get_runtime_password_hash() -> str:
    try:
        from backend.app.services.runtime_settings import get_runtime_setting_value

        password_hash = get_runtime_setting_value(_RUNTIME_PASSWORD_HASH_KEY)
        return str(password_hash or "").strip()
    except Exception:
        return ""


def _persist_runtime_auth(username: str, password_hash: str) -> None:
    try:
        from backend.app.services.runtime_settings import set_runtime_setting_value

        set_runtime_setting_value(_RUNTIME_USERNAME_KEY, username)
        set_runtime_setting_value(_RUNTIME_PASSWORD_HASH_KEY, password_hash)
    except Exception as exc:
        logger.warning("Failed to persist auth defaults: %s", exc)


def auth_configuration_warnings() -> list[str]:
    warnings: list[str] = []
    if not AUTH_ENABLED:
        return warnings
    if AUTH_SECRET_KEY_IS_DEFAULT:
        warnings.append("JWT secret is still using the development default value.")
    if not AUTH_DEFAULT_PASSWORD and not _get_runtime_password_hash():
        warnings.append("No persistent admin password is configured.")
    return warnings


def validate_auth_configuration() -> None:
    warnings = auth_configuration_warnings()
    if not warnings:
        return
    if APP_ENV != "development":
        raise RuntimeError("Authentication is insecure outside development: " + " ".join(warnings))
    for warning in warnings:
        logger.warning("Auth configuration warning: %s", warning)


# In-memory user store (single-user for now, extensible)
_users: dict[str, dict] = {}


def _ensure_default_user() -> None:
    """Create default admin user if none exists."""
    username = _get_runtime_default_username() or AUTH_DEFAULT_USERNAME
    if not username or username in _users:
        return

    stored_password_hash = _get_runtime_password_hash()
    if stored_password_hash:
        _users[username] = {
            "username": username,
            "password_hash": stored_password_hash,
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return

    if APP_ENV == "production" and not AUTH_DEFAULT_PASSWORD:
        raise RuntimeError(
            "MARKET_AI_AUTH_DEFAULT_PASSWORD must be set when authentication is enabled in production."
        )

    password = AUTH_DEFAULT_PASSWORD or secrets.token_urlsafe(16)
    password_hash = _hash_password(password)
    _users[username] = {
        "username": username,
        "password_hash": password_hash,
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if not AUTH_DEFAULT_PASSWORD:
        logger.warning(
            "No AUTH_DEFAULT_PASSWORD set. Generated a temporary in-memory password for the default user. "
            "Set MARKET_AI_AUTH_DEFAULT_PASSWORD for a persistent login.",
        )
        return

    _persist_runtime_auth(username, password_hash)
    logger.info("Default auth user '%s' initialized.", username)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Verify credentials. Returns user dict or None."""
    _ensure_default_user()
    user = _users.get(username)
    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    if not str(user["password_hash"]).startswith(f"{_PBKDF2_PREFIX}$"):
        user["password_hash"] = _hash_password(password)
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
