# ranking-workflow

## Description
Use this skill when updating ranking, long/short summaries, or overall ranked candidate flows.

## When To Use
- Ranking page work
- Scan ranking summaries
- Backend ranking route changes

## Rules
- Top Long = BUY only.
- Top Short = SELL only.
- Overall Ranked can include HOLD.
- Keep `best_setup` sourced from `leaders_optimizer_best.csv` when available.
- Keep `setup_type` as the heuristic label.
