# Deprecation and Alias Map

This file tracks compatibility paths kept intentionally during cleanup.

## Frontend Route Aliases

Canonical route config lives in `frontend/src/routes/appRoutes.jsx`.

- `/paper-trading` -> `/execution`
- `/analyze` -> `/ai-market`
- `/scan` -> `/ranking?mode=scan`
- `/kpis` -> `/`
- `/breadth` -> `/ranking`
- `/risk` -> `/broker`
- `/backtest` -> `/ranking`
- `/strategy-lab` -> `/ranking`
- `/model-lab` -> `/settings`
- `/alerts-center` -> `/execution`
- `/trade-journal` -> `/execution`
- `/automation` -> `/settings`
- `/operations` -> `/settings`
- `/portfolio-exposure` -> `/broker`
- `/macro` -> `/ai-market`
- `/fundamentals` -> `/ai-market`
- `/watchlist` -> `/ranking`
- `/ai-chat` -> `/ai-market`
- `/multi-chart` -> `/live-market`
- `/brain` -> `/settings`

## Backend API Registration Model

Canonical registration map:
- `backend/app/api/route_registry.py`

Compatibility remains via explicit route groups:
- Canonical operator/API surfaces are marked `canonical=true`.
- Legacy/transition surfaces are mounted as compatibility routes without removing endpoints.

## Service Compatibility Facades

- `backend/app/services/automation_hub.py`
  - Kept as facade for existing imports/tests.
  - Delegates to `backend/app/services/automation/` modules.
- `backend/app/services/portfolio_brain.py`
  - Compatibility wrapper around split package modules.

## Workflow Metadata Compatibility

- Canonical workflow docs moved under `docs/dev-workflows/`.
- Root-level files retained as stubs for tooling compatibility:
  - `CLAUDE.md`
  - `LOCAL_LIVE_SERVICES.md`
- `AGENTS.md` remains root-visible and points to canonical copy.
