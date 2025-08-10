from contextlib import asynccontextmanager

from fastapi import FastAPI
from tom_core import __version__
from tom_core import api
from tom_core.credentials.credentials import YamlCredentialStore
from tom_core.config import settings


def create_app():
    @asynccontextmanager
    async def lifespan(this_app: FastAPI):
        # Initialize credential store on startup
        this_app.state.settings = settings
        this_app.state.credential_store = YamlCredentialStore(
            settings.credential_path,
        )
        yield
        # Cleanup on shutdown if needed

    app = FastAPI(
        title="Tom Smykowski Core",
        version=__version__,
        description="Network Automation Broker Service Core.",
        lifespan=lifespan,
    )

    app.include_router(api.router, prefix="/api")
    return app
