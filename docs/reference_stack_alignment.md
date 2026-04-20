# Reference Stack Alignment (April 2026)

This document maps the requested reference repositories to the current Market AI codebase and defines how we adopt them without rewriting working engines (`analysis_engine.py`, `technical_engine.py`, `ranking_engine.py`, `backtest_engine.py`) or breaking `main_ui.py`.

## Current Mapping

| Reference | Adopted In Project | Current Status |
|---|---|---|
| `fastapi/full-stack-fastapi-template` | `backend/` + `frontend/` split, API-first routing, env-driven config | Active base pattern |
| `nautechsystems/nautilus_trader` | Execution contracts + runtime execution services (`backend/app/domain/execution`, `backend/app/application/execution`) | Partially aligned (domain-driven execution, not full framework embed) |
| `OpenBB` | Provider-chain design (`core/market_data_providers.py`) and pluggable market-data seam | Adapter-ready, optional provider extension path |
| `langgraph` | AI orchestration seam through workflow dispatch and background jobs (`backend/app/workflows`, `backend/app/automation`) | Graph-ready architecture, engine logic preserved |
| `fastapi/fastapi` | Main API runtime (`backend/app/main.py`) | Active |
| `sqlalchemy/sqlalchemy` | Persistence and repositories (`backend/app/models`, `backend/app/repositories`) | Active |
| `shadcn-ui/ui` | Design-token driven component structure in `frontend/src/components/ui` | Pattern adopted, selective component parity |
| `TanStack/query` | Frontend server-state strategy (incremental migration path from custom store/hooks) | Planned migration track |
| `boxyhq/saas-starter-kit` | Auth/org-ready architecture seams (`auth`, runtime settings, role-aware process control) | Partially aligned |
| `PrefectHQ/prefect` | Optional heavy-workflow orchestration (`backend/app/services/orchestration_gateway.py`) | Active fallback-capable integration |
| `open-telemetry/opentelemetry-python` | Optional OTel runtime bootstrap (`backend/app/services/open_telemetry.py`) | Added in this patch |
| `prometheus/prometheus` | Scrape endpoint (`/api/metrics`) and metrics summaries | Active |
| `grafana/grafana` | Dashboard-compatible metrics + OTel exporter path | Ready once infra endpoints are configured |

## Production Notes

- Scheduler ownership is role-based by design; API-only processes can now report a delegated scheduler state instead of a false hard-failure state.
- OpenTelemetry is optional and safe-by-default (`MARKET_AI_OTEL_ENABLED=0`).
- Existing optimizer-backed ranking behavior remains unchanged (`leaders_optimizer_best.csv` integration preserved).

## Immediate Next Upgrades

1. Add a dedicated OpenBB provider adapter under `core/market_data_providers.py` with feature flags and fallback safety.
2. Introduce TanStack Query incrementally for high-frequency pages (`Dashboard`, `Settings`, `Live Market`) while preserving current UX behavior.
3. Add Grafana dashboard JSON templates for `/api/metrics` and OTel traces (when collector is enabled).
