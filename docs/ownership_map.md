# Ownership Map

## Core Trading Logic

- Owner scope: signal/analysis semantics and backtest behavior.
- Paths:
  - `analysis_engine.py`
  - `technical_engine.py`
  - `ranking_engine.py`
  - `backtest_engine.py`
  - `leaders_optimizer_best.csv`

## Desktop Surface

- Owner scope: PySide operator workflow stability.
- Paths:
  - `main_ui.py`

## Backend Platform

- Owner scope: API wiring, startup/runtime, auth, config, observability.
- Paths:
  - `backend/app/main.py`
  - `backend/app/config.py`
  - `backend/app/api/`

## Domain Services

- Owner scope: bounded domain behavior and contracts.
- Paths:
  - `backend/app/{market_data,features,strategy,risk,execution,portfolio,broker,automation,research,ai}/`
  - `backend/app/domain/`
  - `backend/app/application/`

## Automation Operations

- Owner scope: cycles, scheduling entrypoints, diagnostics, reconciliation hooks.
- Paths:
  - `backend/app/services/automation/`
  - `backend/app/services/automation_hub.py` (compat facade)

## Portfolio Brain / Decision Surfaces

- Owner scope: signal normalization, action policy, opportunity scoring, explanation payloads.
- Paths:
  - `backend/app/services/portfolio_brain/`
  - `backend/app/services/portfolio_brain.py` (compat facade)
  - `backend/app/services/decision_support.py` (orchestration wrapper)

## Frontend Operator UI

- Owner scope: canonical route surfaces and UX behavior.
- Paths:
  - `frontend/src/routes/`
  - `frontend/src/pages/`
  - `frontend/src/components/`

## Tests and Contracts

- Owner scope: behavior locks for compatibility and regression prevention.
- Paths:
  - `backend/tests/`
  - `frontend/tests/e2e/`

## Documentation and Workflow Metadata

- Owner scope: contributor guidance and migration/deprecation notes.
- Paths:
  - `docs/`
  - `docs/dev-workflows/`
  - root compatibility docs (`AGENTS.md`, `CLAUDE.md`, `LOCAL_LIVE_SERVICES.md`)
