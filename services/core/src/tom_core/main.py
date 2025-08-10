"""ASGI Entrypoint"""

from tom_core.app import create_app

app = create_app()
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "tom_core.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True,
    )
