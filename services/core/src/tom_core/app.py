import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

import saq
from saq.web.starlette import saq_web

from tom_core import __version__
from tom_core import api
from tom_core.config import Settings, settings
from tom_core.inventory.inventory import YamlInventoryStore
from tom_core.inventory.solarwinds import ModifiedSwisClient, SwisInventoryStore
from tom_core.exceptions import (
    TomException,
    TomAuthException,
    TomNotFoundException,
    TomValidationException,
)


def create_queue(settings: Settings) -> saq.Queue:
    queue = saq.Queue.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")
    logging.info(f"Created queue {queue}")
    return queue


def create_app():
    queue = create_queue(settings)

    @asynccontextmanager
    async def lifespan(this_app: FastAPI):
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            force=True  # Override existing logging config
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

    app.mount("/queueMonitor", saq_web("/queueMonitor", [queue]), name="queueMonitor")

    app.include_router(api.router, prefix="/api")

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
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "detail": str(exc)},
        )

    return app
