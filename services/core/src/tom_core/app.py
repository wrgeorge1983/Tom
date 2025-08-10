from contextlib import asynccontextmanager

from fastapi import FastAPI
from tom_core import __version__
from tom_core import api


def create_app():

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(
            title="Tom Smykowski Core",
            version=__version__,
            description="Network Automation Broker Service Core.",
            lifespan=lifespan
    )

    app.include_router(api.router, prefix="/api")
    return app
