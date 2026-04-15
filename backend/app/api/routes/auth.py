"""Authentication routes — login, token refresh, status."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.app.config import AUTH_ENABLED
from backend.app.schemas import AuthStatus
from backend.app.services.auth import (
    auth_configuration_warnings,
    authenticate_user,
    create_access_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Authenticate and receive a JWT token."""
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(user["username"], user.get("role", "admin"))
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user.get("role", "admin"),
    )


@router.get("/status", response_model=AuthStatus)
async def auth_status():
    """Check if authentication is enabled."""
    warnings = auth_configuration_warnings()
    if AUTH_ENABLED:
        return AuthStatus(
            auth_enabled=True,
            detail="Authentication is enabled. POST /auth/login to get a token.",
            warnings=warnings,
        )
    return AuthStatus(
        auth_enabled=False,
        detail="Authentication is disabled. All endpoints are open.",
        warnings=warnings,
    )
