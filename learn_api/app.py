"""应用装配。"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from learn_api.errors import ApiError, api_error_handler, error_response, unhandled_handler
from learn_core.learning.ownership import LearningObjectMissing
from learn_core.learning.creation import CreationConflict
from learn_api.routers import (
    chat, conversations, generation, jobs, materials, me, models, nodes, notes, paths, progress, projects, quizzes, reports, review, search, sources, tools,
)

log = logging.getLogger("learn_api")


class _SPAStaticFiles(StaticFiles):
    """前端是单页应用：刷新 /app/p/123 这类深链接时回落到 index.html。"""

    async def get_response(self, path, scope):
        from starlette.exceptions import HTTPException

        try:
            response = await super().get_response(path, scope)
        except HTTPException:
            return await super().get_response("index.html", scope)
        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


def _mount_web(app):
    """learn_web/dist 存在就挂在 /app 下；不存在（开发或纯 API 部署）就跳过。"""
    from pathlib import Path

    dist = Path(__file__).resolve().parent.parent / "learn_web" / "dist"
    if dist.is_dir():
        app.mount("/app", _SPAStaticFiles(directory=str(dist), html=True), name="learn-web")


def create_app() -> FastAPI:
    app = FastAPI(title="learn-everything-api", version="2.0")

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        if request.url.path.startswith('/api/v2/'):
            response.headers['Cache-Control'] = 'no-store'
        renewed = getattr(request.state, 'authorized_entry_cookie', '')
        if renewed:
            response.headers.append('Set-Cookie', renewed)
        return response

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return await api_error_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        message = f"{'.'.join(str(p) for p in first.get('loc', []))}: {first.get('msg', 'invalid')}"
        return error_response("INVALID_ARGUMENT", message)

    @app.exception_handler(CreationConflict)
    async def _creation_conflict(request: Request, exc: CreationConflict):
        return error_response("CONFLICT", str(exc))

    @app.exception_handler(LearningObjectMissing)
    async def _missing_learning_object(request: Request, exc: LearningObjectMissing):
        return error_response("NOT_FOUND", "learning object not found")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error rid=%s", getattr(request.state, "request_id", "-"))
        return await unhandled_handler(request, exc)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    for module in (
        me, models, projects, nodes, notes, progress, reports, review, quizzes, conversations,
        materials, paths, search, jobs, sources, chat, generation, tools,
    ):
        app.include_router(module.router, prefix="/api/v2")

    # 前端构建产物存在时直接由 API 进程托管，省一个 nginx location。
    _mount_web(app)

    return app


app = create_app()
