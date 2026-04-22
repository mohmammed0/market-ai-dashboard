# Reference Stack Alignment

This document maps external architectural references to the current Market AI codebase.

## Boundary Rule
The live product evolves through `backend/`, `frontend/`, and `core/`.
Legacy engines remain isolated under `legacy/` and are exposed to the modern stack only through explicit adapters in `core/legacy_adapters/`.

## Current Mapping

| Reference | Adopted In Project | Current Status |
|---|---|---|
| `fastapi/full-stack-fastapi-template` | `backend/` + `frontend/` split, API-first routing, env-driven config | Active base pattern |
| `nautechsystems/nautilus_trader` | execution contracts + runtime execution services (`backend/app/domain/execution`, `backend/app/application/execution`) | Partially aligned |
| `OpenBB` | provider-chain design (`core/market_data_providers.py`) | Adapter-ready |
| `langgraph` | workflow dispatch and background jobs (`backend/app/workflows`, `backend/app/automation`) | Graph-ready architecture |
| `sqlalchemy/sqlalchemy` | persistence and repositories (`backend/app/models`, `backend/app/repositories`) | Active |
| `shadcn-ui/ui` | UI structure under `frontend/src/components/ui` | Pattern adopted |
| `PrefectHQ/prefect` | optional workflow orchestration | Active fallback-capable integration |
| `open-telemetry/opentelemetry-python` | optional telemetry bootstrap | Active |
| `prometheus/prometheus` | `/api/metrics` and metrics summaries | Active |

## Notes
- Scheduler ownership is role-based.
- Existing optimizer-backed ranking behavior remains preserved through the legacy adapter boundary.
- Modern routing/bootstrap no longer depends on a monolithic `backend/app/main.py`.
