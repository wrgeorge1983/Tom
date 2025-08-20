import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

import saq
from saq.web.starlette import saq_web

from tom_core import __version__
from tom_core import api
from tom_core.config import Settings, settings
from tom_core.inventory.inventory import YamlInventoryStore


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
        )
        # Initialize credential store on startup
        this_app.state.settings = settings
        this_app.state.inventory_store = YamlInventoryStore(
            settings.inventory_path,
        )
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
    return app
