"""ASGI Entrypoint"""

from tom_core.app import create_app
from tom_core.config import settings

app = create_app()
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "tom_core.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=True,
    )
