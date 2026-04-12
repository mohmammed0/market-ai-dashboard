# Phase 1 Architecture

## Goals
- Preserve the existing desktop application and current signal logic.
- Wrap current engines into reusable `core` services.
- Add a non-breaking FastAPI backend scaffold.
- Add a non-breaking React + Vite frontend scaffold.
- Prepare the backend for SQLAlchemy + Alembic migrations without forcing an immediate DB cutover.

## Target Structure
```text
market_dashboard/
  core/
    analysis_service.py
    technical_service.py
    ranking_service.py
    backtest_service.py
    optimizer_service.py
    live_service.py
  backend/
    app/
      api/
        routes/
      db/
      models/
      schemas/
      main.py
    alembic/
      versions/
    alembic.ini
    requirements.txt
  frontend/
    src/
      components/
      pages/
    package.json
    vite.config.js
  main_ui.py
  analysis_engine.py
  technical_engine.py
  ranking_engine.py
  backtest_engine.py
```

## Migration-Safe Plan
1. Keep root engines as the system of record for business logic during Phase 1.
2. Add `core` wrappers that expose stable service-style entry points without changing engine internals.
3. Build backend API routes against `core` only.
4. Keep the desktop UI working on current imports for now.
5. Introduce backend SQLAlchemy metadata in parallel with the current root DB modules.
6. In a later phase, switch desktop and backend to shared `core` + backend DB packages gradually.
7. Only after parity is proven, consider moving root engines into package locations.

## Notes
- This phase is intentionally scaffold-first, not a full feature migration.
- The backend returns real data for analyze/scan/rank/backtest routes and a safe placeholder for live quotes.
- The frontend is a navigable shell ready to connect to backend routes later.
