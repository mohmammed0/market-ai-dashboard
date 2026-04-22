import logging

from fastapi import FastAPI

from backend.app.config import API_TITLE, API_VERSION, LOG_LEVEL
from backend.app.core.logging_utils import configure_logging
from backend.app.bootstrap.http import configure_middlewares, register_http_middlewares
from backend.app.bootstrap.router_registry import register_routes
from backend.app.bootstrap.runtime import build_lifespan

configure_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title=API_TITLE, version=API_VERSION, lifespan=build_lifespan(logger))
    configure_middlewares(app)
    register_http_middlewares(app, logger)
    register_routes(app)
    return app
