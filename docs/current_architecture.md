# Current Architecture

## Modern Product Boundary
- `backend/` is the live API, automation, broker, readiness, and diagnostics surface.
- `frontend/` is the live operator UI.
- `core/` is the shared service layer for the modern stack.
- `legacy/` is isolated and may only be reached from the modern stack through explicit adapters in `core/legacy_adapters/`.

## Backend
- FastAPI routes live under `backend/app/api/routes`.
- App bootstrap is split across `backend/app/bootstrap/`:
  - `app_factory.py`
  - `router_registry.py`
  - `runtime.py`
  - `http.py`
- `backend/app/application/` contains orchestration/application services.
- `backend/app/domain/` contains internal contracts and domain boundaries.
- `backend/app/repositories/` and `backend/app/models/` own persistence.
- `backend/app/services/` contains runtime integrations, diagnostics, market data, readiness, portfolio brain, and automation.

## Frontend
- React/Vite SPA under `frontend/`.
- App composition is split through `frontend/src/app/` instead of overloading `frontend/src/App.jsx`.
- Domain API calls live under `frontend/src/api/`.
- Shared layout/components live under `frontend/src/components/`.

## Legacy
- `legacy/engines/` preserves old engine logic.
- `legacy/ui/main_ui.py` preserves the desktop app.
- `legacy/support/` preserves old DB/support helpers needed by the desktop stack.
- `legacy/scripts/` preserves old one-off workers and maintenance scripts.

## Execution Truth
- Broker-managed account/order/position/execution state is the only active truth.
- Internal paper trading is not part of the live path.
