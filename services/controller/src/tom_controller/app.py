import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import saq
from saq.web.starlette import saq_web

from tom_controller import __version__
from tom_controller import api
from tom_controller.config import Settings, settings
from tom_controller.inventory.inventory import YamlInventoryStore
from tom_controller.inventory.solarwinds import ModifiedSwisClient, SwisInventoryStore
from tom_controller.exceptions import (
    TomException,
    TomAuthException,
    TomNotFoundException,
    TomValidationException,
)


def create_queue(settings: Settings) -> saq.Queue:
    queue = saq.Queue.from_url(settings.redis_url)
    logging.info(f"Created queue {queue}")
    return queue


def create_app():
    queue = create_queue(settings)

    @asynccontextmanager
    async def lifespan(this_app: FastAPI):
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            force=True,  # Override existing logging config
        )
        logger = logging.getLogger(__name__)

        print(f"DEBUG: Log level set to: {logging.getLevelName(settings.log_level)}")

        # Initialize inventory store on startup
        this_app.state.settings = settings

        logger.info(
            f"Initializing inventory store with type: {settings.inventory_type}"
        )

        if settings.inventory_type == "yaml":
            logger.info(f"Using YAML inventory from: {settings.inventory_path}")
            this_app.state.inventory_store = YamlInventoryStore(settings.inventory_path)
        elif settings.inventory_type == "swis":
            logger.info(f"Using SWIS inventory with host: {settings.swapi_host}")
            swis_client = ModifiedSwisClient.from_settings(settings)
            this_app.state.inventory_store = SwisInventoryStore(swis_client, settings)
        else:
            raise ValueError(f"Unknown inventory_type: {settings.inventory_type}")
        this_app.state.queue = queue
        yield
        # Cleanup on shutdown if needed

    app = FastAPI(
        title="Tom Smykowski Core",
        version=__version__,
        description="Network Automation Broker Service Core.",
        lifespan=lifespan,
    )

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            summary=app.summary,
            description=app.description,
            routes=app.routes,
        )
        openapi_schema["info"]["x-logo"] = {
            "url": "static/Tom-BlkWhiteTrans_1000x1000.png"
        }
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.mount(
        "/static",
        StaticFiles(
            directory=f"{settings.project_root}/services/controller/src/tom_controller/static"
        ),
        name="static",
    )

    app.openapi = custom_openapi

    app.mount("/queueMonitor", saq_web("/queueMonitor", [queue]), name="queueMonitor")

    app.include_router(api.router, prefix="/api")
    app.include_router(
        api.oauth_router, prefix="/api"
    )  # OAuth endpoints don't require auth

    # Exception handlers
    @app.exception_handler(TomAuthException)
    async def auth_exception_handler(request: Request, exc: TomAuthException):
        return JSONResponse(
            status_code=401, content={"error": "Unauthorized", "detail": str(exc)}
        )

    @app.exception_handler(TomNotFoundException)
    async def not_found_exception_handler(request: Request, exc: TomNotFoundException):
        return JSONResponse(
            status_code=404, content={"error": "Not Found", "detail": str(exc)}
        )

    @app.exception_handler(TomValidationException)
    async def validation_exception_handler(
        request: Request, exc: TomValidationException
    ):
        return JSONResponse(
            status_code=400, content={"error": "Bad Request", "detail": str(exc)}
        )

    @app.exception_handler(TomException)
    async def tom_exception_handler(request: Request, exc: TomException):
        import traceback
        import sys

        # Log the full exception with stack trace
        logging.error(f"TomException occurred: {exc}")
        logging.error("".join(traceback.format_exception(*sys.exc_info())))

        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        import traceback

        # Log the full exception with stack trace
        logging.error(f"Unhandled exception occurred: {exc}")
        logging.error("Full traceback:")
        logging.error(traceback.format_exc())

        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "detail": str(exc)},
        )

    return app
