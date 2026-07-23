# SPDX-License-Identifier: AGPL-3.0-only
"""Consistent error envelope: every failure returns {code, message, fields?}.

Matches the frontend `ApiError` contract so the UI can localise by `errors.<code>`.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Domain error carrying a stable machine code, an HTTP status and optional field errors."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        fields: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.fields = fields


def _envelope(code: str, message: str, fields: dict[str, str] | None = None) -> dict[str, object]:
    body: dict[str, object] = {"code": code, "message": message}
    if fields:
        body["fields"] = fields
    return body


# HTTP status -> default stable code, so bare HTTPExceptions still yield a coded envelope.
_STATUS_CODE = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.fields),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
            fields[loc or "_"] = err["msg"]
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(_envelope("VALIDATION_ERROR", "Validation failed", fields)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # fastapi-users and framework guards raise plain HTTPExceptions; give them a coded envelope.
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            code = str(detail.get("code"))
            message = str(detail.get("reason", detail.get("message", code)))
        else:
            code = _STATUS_CODE.get(exc.status_code, "ERROR")
            message = str(detail) if detail else code
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, message))
