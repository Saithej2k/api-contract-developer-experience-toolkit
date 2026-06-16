from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    auth_missing = "AUTH_MISSING"
    forbidden = "FORBIDDEN"
    idempotency_key_required = "IDEMPOTENCY_KEY_REQUIRED"
    idempotency_conflict = "IDEMPOTENCY_CONFLICT"
    unsupported_schema_version = "UNSUPPORTED_SCHEMA_VERSION"
    not_found = "NOT_FOUND"
    validation_failed = "VALIDATION_FAILED"
    replay_not_allowed = "REPLAY_NOT_ALLOWED"
    conflict = "CONFLICT"


class ErrorResponse(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            request_id=request_id,
        ).model_dump(mode="json"),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID")
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            code=ErrorCode.validation_failed,
            message="Request validation failed.",
            details={"errors": exc.errors()},
            request_id=request_id,
        ).model_dump(mode="json"),
    )
