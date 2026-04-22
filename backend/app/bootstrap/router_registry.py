from fastapi import FastAPI

from backend.app.bootstrap.route_groups import API_ROUTERS, PUBLIC_ROUTERS


def register_routes(app: FastAPI) -> None:
    for router in PUBLIC_ROUTERS:
        app.include_router(router)
    for router in API_ROUTERS:
        app.include_router(router, prefix="/api")
