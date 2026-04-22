# Legacy Boundary

This directory contains the pre-modern engine layer, desktop UI, and older operational scripts.

## Rules
- The live product must not import legacy modules directly.
- Modern code reaches legacy code only through explicit adapters in `core/legacy_adapters/`.
- Legacy modules may continue to depend on each other internally.
- Legacy tooling can remain functional, but it is not the primary production path.

## Layout
- `legacy/engines/` — old market/analysis/ranking/backtest/news/ML engines
- `legacy/ui/` — old desktop UI
- `legacy/support/` — old database/support modules
- `legacy/scripts/` — old training, optimizer, worker, and maintenance scripts
