from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from backend.app.config import (
    API_VERSION,
    APP_ENV,
    OTEL_CONSOLE_EXPORTER_ENABLED,
    OTEL_ENABLED,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_INSECURE,
    OTEL_INSTRUMENT_REQUESTS_ENABLED,
    OTEL_SERVICE_NAME,
)
from backend.app.core.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class _RuntimeState:
    enabled: bool
    active: bool
    runtime: str
    detail: str
    service_name: str
    exporters: list[str]
    endpoint: str | None
    instrumented_apps: int
    requests_instrumented: bool


_state_lock = Lock()
_instrumented_app_ids: set[int] = set()
_requests_instrumented = False
_runtime_state = _RuntimeState(
    enabled=bool(OTEL_ENABLED),
    active=False,
    runtime="disabled" if not OTEL_ENABLED else "pending",
    detail="OpenTelemetry is disabled by configuration." if not OTEL_ENABLED else "OpenTelemetry is not initialized yet.",
    service_name=OTEL_SERVICE_NAME,
    exporters=[],
    endpoint=OTEL_EXPORTER_OTLP_ENDPOINT or None,
    instrumented_apps=0,
    requests_instrumented=False,
)


def _load_sdk() -> dict[str, Any]:
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    modules: dict[str, Any] = {
        "trace": trace,
        "FastAPIInstrumentor": FastAPIInstrumentor,
        "SERVICE_NAME": SERVICE_NAME,
        "SERVICE_VERSION": SERVICE_VERSION,
        "Resource": Resource,
        "TracerProvider": TracerProvider,
        "BatchSpanProcessor": BatchSpanProcessor,
        "ConsoleSpanExporter": ConsoleSpanExporter,
    }

    if OTEL_INSTRUMENT_REQUESTS_ENABLED:
        try:
            from opentelemetry.instrumentation.requests import RequestsInstrumentor
        except Exception:
            modules["RequestsInstrumentor"] = None
        else:
            modules["RequestsInstrumentor"] = RequestsInstrumentor

    if OTEL_EXPORTER_OTLP_ENDPOINT:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        except Exception:
            modules["OTLPSpanExporter"] = None
        else:
            modules["OTLPSpanExporter"] = OTLPSpanExporter

    return modules


def _initialize_global_provider(modules: dict[str, Any]) -> tuple[bool, str, list[str]]:
    trace = modules["trace"]
    Resource = modules["Resource"]
    TracerProvider = modules["TracerProvider"]
    BatchSpanProcessor = modules["BatchSpanProcessor"]
    ConsoleSpanExporter = modules["ConsoleSpanExporter"]
    SERVICE_NAME = modules["SERVICE_NAME"]
    SERVICE_VERSION = modules["SERVICE_VERSION"]

    providers = []
    provider = TracerProvider(
        resource=Resource.create(
            {
                SERVICE_NAME: OTEL_SERVICE_NAME,
                SERVICE_VERSION: API_VERSION,
                "deployment.environment": APP_ENV,
            }
        )
    )

    if OTEL_EXPORTER_OTLP_ENDPOINT:
        exporter_cls = modules.get("OTLPSpanExporter")
        if exporter_cls is None:
            return (
                False,
                "OTLP endpoint configured, but OTLP exporter package is missing.",
                providers,
            )
        provider.add_span_processor(
            BatchSpanProcessor(
                exporter_cls(
                    endpoint=OTEL_EXPORTER_OTLP_ENDPOINT,
                    insecure=OTEL_EXPORTER_OTLP_INSECURE,
                )
            )
        )
        providers.append("otlp_http")

    if OTEL_CONSOLE_EXPORTER_ENABLED:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        providers.append("console")

    if not providers:
        return (
            False,
            "No exporter configured. Set MARKET_AI_OTEL_EXPORTER_OTLP_ENDPOINT or MARKET_AI_OTEL_CONSOLE_EXPORTER_ENABLED=1.",
            providers,
        )

    try:
        trace.set_tracer_provider(provider)
    except Exception:
        # Another tracer provider may already be active in-process.
        pass
    return True, "OpenTelemetry tracer provider initialized.", providers


def bootstrap_open_telemetry(app=None) -> dict[str, Any]:
    global _requests_instrumented

    with _state_lock:
        if not OTEL_ENABLED:
            _runtime_state.enabled = False
            _runtime_state.active = False
            _runtime_state.runtime = "disabled"
            _runtime_state.detail = "OpenTelemetry is disabled by configuration."
            _runtime_state.exporters = []
            _runtime_state.endpoint = OTEL_EXPORTER_OTLP_ENDPOINT or None
            _runtime_state.service_name = OTEL_SERVICE_NAME
            _runtime_state.requests_instrumented = False
            _runtime_state.instrumented_apps = len(_instrumented_app_ids)
            return get_open_telemetry_status()

        try:
            modules = _load_sdk()
        except Exception as exc:
            _runtime_state.enabled = True
            _runtime_state.active = False
            _runtime_state.runtime = "misconfigured"
            _runtime_state.detail = f"OpenTelemetry packages are not installed: {exc.__class__.__name__}"
            _runtime_state.exporters = []
            _runtime_state.endpoint = OTEL_EXPORTER_OTLP_ENDPOINT or None
            _runtime_state.service_name = OTEL_SERVICE_NAME
            _runtime_state.requests_instrumented = False
            _runtime_state.instrumented_apps = len(_instrumented_app_ids)
            return get_open_telemetry_status()

        active, detail, exporters = _initialize_global_provider(modules)
        _runtime_state.enabled = True
        _runtime_state.active = bool(active)
        _runtime_state.runtime = "ready" if active else "misconfigured"
        _runtime_state.detail = detail
        _runtime_state.exporters = exporters
        _runtime_state.endpoint = OTEL_EXPORTER_OTLP_ENDPOINT or None
        _runtime_state.service_name = OTEL_SERVICE_NAME

        if app is not None and active:
            app_id = id(app)
            if app_id not in _instrumented_app_ids:
                modules["FastAPIInstrumentor"].instrument_app(app, tracer_provider=modules["trace"].get_tracer_provider())
                _instrumented_app_ids.add(app_id)

        if (
            active
            and OTEL_INSTRUMENT_REQUESTS_ENABLED
            and not _requests_instrumented
            and modules.get("RequestsInstrumentor") is not None
        ):
            modules["RequestsInstrumentor"]().instrument()
            _requests_instrumented = True

        _runtime_state.requests_instrumented = _requests_instrumented
        _runtime_state.instrumented_apps = len(_instrumented_app_ids)
        return get_open_telemetry_status()


def get_open_telemetry_status() -> dict[str, Any]:
    return {
        "enabled": _runtime_state.enabled,
        "active": _runtime_state.active,
        "runtime": _runtime_state.runtime,
        "detail": _runtime_state.detail,
        "service_name": _runtime_state.service_name,
        "exporters": list(_runtime_state.exporters),
        "endpoint": _runtime_state.endpoint,
        "instrumented_apps": int(_runtime_state.instrumented_apps),
        "requests_instrumented": bool(_runtime_state.requests_instrumented),
    }


__all__ = ["bootstrap_open_telemetry", "get_open_telemetry_status"]
