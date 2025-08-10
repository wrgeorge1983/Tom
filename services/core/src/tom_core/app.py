from contextlib import asynccontextmanager

from fastapi import FastAPI
from tom_core import __version__


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
