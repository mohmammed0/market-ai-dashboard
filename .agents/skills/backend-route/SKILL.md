# backend-route

## Description
Use this skill when adding or patching FastAPI routes in this project.

## When To Use
- New backend endpoints
- Route resilience fixes
- Dashboard/API summary work

## Rules
- Keep endpoint shapes stable when possible.
- Route code should call `core/` wrappers, not UI files.
- Per-symbol failures must not crash batch routes.
- External news failure must degrade gracefully.
- Prefer additive changes over route rewrites.
