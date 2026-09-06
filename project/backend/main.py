from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.health import router as health_router
from .config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[app_settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(health_router)
    application.state.settings = app_settings
    return application


app = create_app()
