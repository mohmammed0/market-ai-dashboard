from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.app.config import (
    ALLOWED_ORIGINS,
    APP_ENV,
    AUTH_ENABLED,
    FORWARDED_ALLOW_IPS,
    PROXY_HEADERS_ENABLED,
    TRUSTED_HOSTS,
)
from backend.app.core.logging_utils import log_event

_PUBLIC_PREFIXES = ("/auth", "/health", "/docs", "/openapi.json", "/redoc")


def _is_worker_token_path(path: str) -> bool:
    if path.startswith("/api/training/worker"):
        return True
    if path == "/api/training/jobs/next-queued":
        return True
    return path.startswith("/api/training/jobs/") and (path.endswith("/claim") or path.endswith("/artifact"))


def configure_middlewares(app: FastAPI) -> None:
    if PROXY_HEADERS_ENABLED:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=FORWARDED_ALLOW_IPS)

    if TRUSTED_HOSTS and "*" not in TRUSTED_HOSTS:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def register_http_middlewares(app: FastAPI, logger: logging.Logger) -> None:
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if not AUTH_ENABLED:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES) or _is_worker_token_path(path):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            from starlette.responses import JSONResponse

            return JSONResponse(status_code=401, content={"detail": "Authentication required. POST /auth/login to get a token."})

        token = auth_header[7:]
        try:
            from backend.app.services.auth import decode_token

            decode_token(token)
        except Exception:
            from starlette.responses import JSONResponse

            return JSONResponse(status_code=401, content={"detail": "Invalid or expired token."})

        return await call_next(request)

    @app.middleware("http")
    async def request_observer(request: Request, call_next):
        request_id = uuid4().hex[:12]
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "api.request.exception",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                client=None if request.client is None else request.client.host,
                environment=APP_ENV,
                error=str(exc),
            )
            raise

        duration_ms = round((perf_counter() - started) * 1000.0, 2)
        if response.status_code >= 400:
            log_event(
                logger,
                logging.WARNING if response.status_code < 500 else logging.ERROR,
                "api.request.error",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client=None if request.client is None else request.client.host,
            )
        response.headers["X-Request-ID"] = request_id
        return response
