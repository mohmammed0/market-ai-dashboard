# market-analyze

## Description
Use this skill when implementing or modifying single-symbol analysis features in this repo.

## When To Use
- Analyze page changes
- Backend `/api/analyze` work
- Analysis result display updates

## Rules
- Reuse legacy analysis through `core/analysis_service.py` and `core/legacy_adapters/analysis.py`.
- Preserve `best_setup`, `confidence`, and `setup_type`.
- Keep loading, error, empty, and degraded-news states visible.
- Do not break the desktop UI analysis flow.
