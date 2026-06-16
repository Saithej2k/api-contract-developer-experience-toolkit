from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.v1 import router as v1_router
from backend.app.core.config import settings
from backend.app.core.errors import ApiError, api_error_handler, validation_error_handler
from backend.app.db import SessionLocal, init_db
from backend.app.seed import seed_database
from fastapi.exceptions import RequestValidationError


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Production-style API contract and developer experience toolkit.",
        contact={"name": "API Platform Team"},
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(v1_router)

    @app.on_event("startup")
    def startup() -> None:
        init_db()
        if settings.seed_on_startup:
            db = SessionLocal()
            try:
                seed_database(db)
                db.commit()
            finally:
                db.close()

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "schema_version": settings.current_schema_version,
        }

    return app


app = create_app()
