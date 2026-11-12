"""应用装配。"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from learn_api.errors import ApiError, api_error_handler, error_response, unhandled_handler
from learn_api.routers import chat, jobs, projects, search, sources

log = logging.getLogger("learn_api")


def create_app() -> FastAPI:
    app = FastAPI(title="learn-everything-api", version="2.0")

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return await api_error_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        message = f"{'.'.join(str(p) for p in first.get('loc', []))}: {first.get('msg', 'invalid')}"
        return error_response("INVALID_ARGUMENT", message)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error rid=%s", getattr(request.state, "request_id", "-"))
        return await unhandled_handler(request, exc)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    for module in (projects, search, jobs, sources, chat):
        app.include_router(module.router, prefix="/api/v2")

    return app


app = create_app()
