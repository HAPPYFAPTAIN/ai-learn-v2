"""应用装配。"""

from __future__ import annotations

import logging
import uuid
import re
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from starlette.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError
from learn_api.auth import validate_dev_auth

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from learn_api.errors import ApiError, api_error_handler, error_response, unhandled_handler
from learn_core.learning.ownership import LearningObjectMissing
from learn_core.learning.creation import CreationConflict
from learn_core.llm.providers import ProviderError
from learn_api.routers import (
    assistant, conversations, generation, jobs, materials, me, models, nodes, notes, paths, progress, projects, providers, quizzes, reports, review, search, tools,
)

log = logging.getLogger("learn_api")
SECURITY_HEADERS = {
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'same-origin',
}


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
    @asynccontextmanager
    async def lifespan(app):
        validate_dev_auth()
        yield

    app = FastAPI(title="learn-everything-api", version="2.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        supplied = request.headers.get("X-Request-Id", "")
        rid = supplied if re.fullmatch(r"[A-Za-z0-9-]{1,64}", supplied) else uuid.uuid4().hex
        request.state.request_id = rid
        try:
            response = await call_next(request)
        except Exception:
            request.state.error_code = 'INTERNAL'
            response = error_response('INTERNAL', '服务暂时不可用，请稍后重试')
        if response.status_code >= 400:
            log.warning('api_error time=%s method=%s path=%s status=%s code=%s account=%s request_id=%s',
                        datetime.now(timezone.utc).isoformat(), request.method,
                        re.sub(r'[\r\n\t]', '_', request.url.path), response.status_code,
                        getattr(request.state, 'error_code', 'HTTP_ERROR'),
                        re.sub(r'[^A-Za-z0-9_-]', '_', getattr(request.state, 'account_id', '-'))[:8], rid)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        response.headers["X-Request-Id"] = rid
        if request.url.path.startswith('/api/v2/'):
            response.headers['Cache-Control'] = 'no-store'
        renewed = getattr(request.state, 'authorized_entry_cookie', '')
        if renewed:
            response.headers.append('Set-Cookie', renewed)
        return response

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        request.state.error_code = exc.code
        return await api_error_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = '.'.join(str(p) for p in first.get('loc', []) if p not in {'body', 'query', 'path'}) or '请求参数'
        request.state.error_code = 'INVALID_ARGUMENT'
        return error_response("INVALID_ARGUMENT", f"输入不符合要求：{field}")

    @app.exception_handler(CreationConflict)
    async def _creation_conflict(request: Request, exc: CreationConflict):
        request.state.error_code = 'CONFLICT'
        return error_response("CONFLICT", str(exc))

    @app.exception_handler(ProviderError)
    async def _provider_error(request: Request, exc: ProviderError):
        request.state.error_code = exc.code
        return error_response(exc.code, str(exc))

    @app.exception_handler(LearningObjectMissing)
    async def _missing_learning_object(request: Request, exc: LearningObjectMissing):
        request.state.error_code = 'NOT_FOUND'
        return error_response("NOT_FOUND", "learning object not found")

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        request.state.error_code = 'NOT_FOUND' if exc.status_code == 404 else 'HTTP_ERROR'
        return JSONResponse({'error': {'code': request.state.error_code, 'message': '请求路径不存在' if exc.status_code == 404 else '请求无法处理', 'retryable': False}}, status_code=exc.status_code)

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        constraint = getattr(getattr(exc.orig, 'diag', None), 'constraint_name', '')
        if constraint == 'uq_le_knode_project_code':
            request.state.error_code = 'CONFLICT'
            return error_response('CONFLICT', '章节编号已存在')
        request.state.error_code = 'INTERNAL'
        return error_response('INTERNAL', '数据保存失败，请稍后重试')

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        request.state.error_code = 'INTERNAL'
        return await unhandled_handler(request, exc)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    for module in (
        assistant, me, models, providers, projects, nodes, notes, progress, reports, review, quizzes, conversations,
        materials, paths, search, jobs, generation, tools,
    ):
        app.include_router(module.router, prefix="/api/v2")

    # 前端构建产物存在时直接由 API 进程托管，省一个 nginx location。
    _mount_web(app)

    return app


app = create_app()
