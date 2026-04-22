# Phase 1 Architecture (Historical Reference)

This document is kept as historical context.

## Original Goal
- preserve the desktop application and existing signal logic
- add non-breaking `core/`, backend, and frontend layers
- prepare the system for gradual migration

## Actual Current Outcome
The repository has now moved beyond the original phase-1 shape:
- the live product is the modern stack under `backend/`, `frontend/`, `core/`, and `scripts/`
- old engines and the desktop UI are isolated under `legacy/`
- the modern stack reaches legacy logic only through `core/legacy_adapters/`
- app bootstrap is split into dedicated modules under `backend/app/bootstrap/`

Use `docs/current_architecture.md` for the current layout.
