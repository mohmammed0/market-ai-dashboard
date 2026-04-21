# Repository Map

This map prioritizes product-runtime code first, then contributor workflow metadata.

## 1) Product Runtime Surfaces

- Root engines (source-of-truth signal logic)
  - `analysis_engine.py`
  - `technical_engine.py`
  - `ranking_engine.py`
  - `backtest_engine.py`
- Desktop operator app
  - `main_ui.py`
- Shared wrappers
  - `core/`
- Backend API + domain services
  - `backend/app/`
- Frontend operator UI
  - `frontend/src/`
- Data/model/runtime assets
  - `data/`
  - `model_artifacts/`
  - `seed_data/`

## 2) Domain Boundaries (Backend)

- `backend/app/market_data/` and `backend/app/adapters/market_data/`
- `backend/app/features/`
- `backend/app/strategy/`
- `backend/app/risk/` and `backend/app/domain/risk/`
- `backend/app/execution/` and `backend/app/domain/execution/`
- `backend/app/portfolio/` and `backend/app/domain/portfolio/`
- `backend/app/broker/` and `backend/app/domain/broker/`
- `backend/app/automation/` and `backend/app/services/automation/`
- `backend/app/research/`
- `backend/app/ai/`

## 3) Service Split Highlights

- Automation hub split
  - Compatibility facade: `backend/app/services/automation_hub.py`
  - Core modules: `backend/app/services/automation/`
    - `orchestration.py`
    - `cycles.py`
    - `auto_trading.py`
    - `persistence.py`
    - `common.py`
- Portfolio brain split
  - Compatibility module: `backend/app/services/portfolio_brain.py`
  - Core modules: `backend/app/services/portfolio_brain/`

## 4) API Route Registration

- Canonical route mount map:
  - `backend/app/api/route_registry.py`
- App wiring:
  - `backend/app/main.py`

## 5) Frontend Routing

- Central canonical + alias routing:
  - `frontend/src/routes/appRoutes.jsx`
  - `frontend/src/routes/pageLoaders.js`
- App router entry:
  - `frontend/src/App.jsx`

## 6) Workflow Metadata (Grouped)

- Canonical workflow guidance:
  - `docs/dev-workflows/AGENTS.md`
  - `docs/dev-workflows/CLAUDE.md`
  - `docs/dev-workflows/LOCAL_LIVE_SERVICES.md`
- Root compatibility stubs retained for tooling:
  - `CLAUDE.md`
  - `LOCAL_LIVE_SERVICES.md`
