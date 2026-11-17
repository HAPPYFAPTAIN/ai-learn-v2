"""Optional loopback-only test gateway; never imported by the official application.

Keys stay in this process's memory. Restarting clears imported providers.
Use one uvicorn process and route local API/workers through /v1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hmac import compare_digest
import ipaddress
import os
import socket
from threading import RLock
from time import monotonic
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, SecretStr

from learn_api.errors import ApiError, api_error_handler

LOCAL_USER = 'dev-local-roadmap-test'


class ProviderInput(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    baseUrl: str = Field(min_length=1, max_length=500)
    apiKey: SecretStr = Field(min_length=1, max_length=4096)
    models: list[str] = Field(min_length=1, max_length=100)
    remark: str = Field(default='', max_length=200)
    website: str = Field(default='', max_length=500)


def public_endpoint(value: str) -> str:
    """HTTPS public APIs only; redirects and environment proxies are disabled."""
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        raise ApiError('INVALID_ARGUMENT', 'API 地址格式无效') from None
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or port not in {None, 443}):
        raise ApiError('INVALID_ARGUMENT', '请使用公开的 HTTPS OpenAI 兼容地址（443 端口），不要包含密钥或查询参数')
    try:
        addresses = socket.getaddrinfo(url.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ApiError('INVALID_ARGUMENT', '无法解析供应商地址，请检查 API 地址') from None
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ApiError('INVALID_ARGUMENT', '此测试入口仅支持公开模型 API，不支持内网、本机或元数据地址')
    return value.rstrip('/')


@dataclass
class Connection:
    id: str
    provider: str
    name: str
    base_url: str
    key: str = field(repr=False)
    models: dict[str, str] = field(default_factory=dict)
    remark: str = ''
    website: str = ''

    def metadata(self):
        return {'id': self.id, 'provider': self.provider, 'name': self.name,
                'baseUrl': self.base_url, 'models': list(self.models),
                'remark': self.remark, 'website': self.website}


class LocalRegistry:
    def __init__(self, token: str, *, transport=None):
        self.token = token
        self.transport = transport
        self.connections: dict[str, Connection] = {}
        self.lock = RLock()
        key = os.environ.get('DEEPSEEK_API_KEY', '')
        if key:
            self.connections['default'] = Connection(
                'default', 'deepseek', 'DeepSeek（启动配置）',
                'https://api.deepseek.com/v1', key,
                {'deepseek-flash': 'deepseek-flash', 'deepseek-v4-pro': 'deepseek-v4-pro'})

    def call(self, connection: Connection, method: str, path: str, *, payload=None):
        # Pin the checked address, preserving the hostname for TLS verification.
        base = public_endpoint(connection.base_url)
        parsed = urlsplit(base)
        try:
            addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        except OSError:
            raise ApiError('GATEWAY_UNAVAILABLE', '无法解析供应商地址') from None
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ApiError('INVALID_ARGUMENT', 'API 地址必须解析为公网地址')
        address = addresses[0][4][0]
        authority = f'[{address}]' if ':' in address else address
        pinned = urlunsplit(('https', authority, parsed.path + path, '', ''))
        try:
            with httpx.Client(timeout=120 if method == 'POST' else 15,
                              follow_redirects=False, trust_env=False,
                              transport=self.transport) as client:
                response = client.request(method, pinned, json=payload,
                                          headers={'Authorization': f'Bearer {connection.key}', 'Host': parsed.hostname},
                                          extensions={'sni_hostname': parsed.hostname})
        except httpx.HTTPError:
            raise ApiError('GATEWAY_UNAVAILABLE', '模型 API 连接失败或超时，请检查地址和网络') from None
        if not 200 <= response.status_code < 300:
            hint = ('Key 无效或没有模型权限' if response.status_code in {401, 403}
                    else '请求受限，请检查额度、模型 ID 和接口兼容性')
            raise ApiError('INVALID_ARGUMENT', f'供应商返回 HTTP {response.status_code}：{hint}')
        try:
            return response.json()
        except ValueError:
            raise ApiError('INVALID_ARGUMENT', '供应商未返回有效的 JSON 数据') from None

    def add(self, payload: ProviderInput):
        ids = list(dict.fromkeys(m.strip() for m in payload.models))
        if any(not m or len(m) > 100 or any(ord(c) < 32 for c in m) for m in ids):
            raise ApiError('INVALID_ARGUMENT', '模型 ID 不能为空，且不能超过 100 个字符')
        key = payload.apiKey.get_secret_value().strip()
        if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ApiError('INVALID_ARGUMENT', '请检查 API Key，不能包含空格或换行')
        if not payload.name.strip():
            raise ApiError('INVALID_ARGUMENT', '请填写供应商名称')
        cid = uuid4().hex[:12]
        connection = Connection(cid, payload.provider, payload.name.strip(),
                                public_endpoint(payload.baseUrl.strip()), key,
                                {f'local.{cid}.{mid}': mid for mid in ids},
                                payload.remark, payload.website)
        started = monotonic()
        data = self.call(connection, 'GET', '/models')
        try:
            rows = data['data']
            if not isinstance(rows, list) or len(rows) > 2000:
                raise ValueError()
            available = {row['id'] for row in rows if isinstance(row, dict) and isinstance(row.get('id'), str)}
            if any(mid not in available for mid in ids):
                raise ApiError('INVALID_ARGUMENT', '部分模型 ID 不在供应商返回的列表中，请填写当前账号可用的模型 ID')
        except (TypeError, KeyError, ValueError):
            raise ApiError('INVALID_ARGUMENT', '此入口需要兼容 OpenAI 的 /models 和 /chat/completions 接口') from None
        with self.lock:
            if len(self.connections) >= 20:
                raise ApiError('INVALID_ARGUMENT', '本次测试最多添加 20 个供应商，重启测试服务可清空')
            if any(c.name == connection.name for c in self.connections.values()):
                raise ApiError('CONFLICT', '供应商名称已存在，请使用不同名称')
            self.connections[cid] = connection
        return {'connection': connection.metadata(), 'verifiedMs': round((monotonic() - started) * 1000)}

    def catalog(self):
        with self.lock:
            return [{'id': mid, 'object': 'model', 'owned_by': c.id}
                    for c in self.connections.values() for mid in c.models]


def create_proxy(token: str, *, transport=None):
    if os.environ.get('LEARN_DEV_AUTH') != '1' or len(token) < 32:
        raise RuntimeError('Local proxy requires dev auth and an ephemeral secret')
    registry = LocalRegistry(token, transport=transport)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.registry = registry
    app.add_exception_handler(ApiError, api_error_handler)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        # Never echo Pydantic's original input, which could include a key.
        return JSONResponse({'error': {'code': 'INVALID_ARGUMENT',
                            'message': '供应商配置格式无效，请检查名称、地址、Key 和模型 ID',
                            'retryable': False}}, status_code=422)

    @app.middleware('http')
    async def guard(request: Request, call_next):
        if (not request.client or request.client.host not in {'127.0.0.1', 'testclient'}
                or request.url.hostname not in {'127.0.0.1', 'testserver'}
                or not compare_digest(request.headers.get('Authorization', '').encode(), f'Bearer {token}'.encode())):
            return JSONResponse({'error': 'local gateway unavailable'}, status_code=403)
        if request.url.path.startswith('/v1') and request.headers.get('X-End-User') != LOCAL_USER:
            return JSONResponse({'error': 'local test account required'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/providers')
    def providers():
        with registry.lock:
            return {'enabled': True, 'connections': [c.metadata() for c in registry.connections.values()]}

    @app.post('/providers')
    def add(payload: ProviderInput):
        return registry.add(payload)

    @app.get('/v1/models')
    def models():
        return {'data': registry.catalog()}

    @app.post('/v1/chat/completions')
    async def chat(request: Request):
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get('model'), str):
            raise ApiError('INVALID_ARGUMENT', '模型请求格式无效')
        mid = payload.get('model')
        with registry.lock:
            connection = next((c for c in registry.connections.values() if mid in c.models), None)
        if connection is None:
            raise ApiError('INVALID_ARGUMENT', '本地测试供应商已失效，请重新添加并选择主模型')
        payload['model'] = connection.models[mid]
        # Blocking upstream work is isolated from the ASGI event loop.
        from starlette.concurrency import run_in_threadpool
        result = await run_in_threadpool(registry.call, connection, 'POST', '/chat/completions', payload=payload)
        # Preserve the local routing identity in task/cost records, without exposing credentials.
        if isinstance(result, dict):
            result['model'] = mid
        return result

    return app


def attach_local_controls(app: FastAPI, *, proxy_url: str, token: str):
    """Called only from the separate local entrypoint, not create_app()."""
    if os.environ.get('LEARN_DEV_AUTH') != '1' or proxy_url != 'http://127.0.0.1:18091':
        raise RuntimeError('Local provider controls require the isolated loopback test launcher')
    from learn_api.auth import get_principal

    def gate(request: Request, principal=Depends(get_principal)):
        if (request.url.hostname != '127.0.0.1' or request.client.host != '127.0.0.1'
                or principal.official_user_id != LOCAL_USER
                or request.headers.get('X-Learn-Expected-User') != LOCAL_USER):
            raise ApiError('NOT_FOUND', '本地测试入口不可用')
        if request.method == 'POST' and (
                request.headers.get('Origin') not in {'http://127.0.0.1:5173', 'http://127.0.0.1:8000'}
                or request.headers.get('Sec-Fetch-Site') in {'cross-site', 'same-site'}):
            raise ApiError('INVALID_ARGUMENT', '请在本机测试页面添加供应商')

    def forward(method, payload=None):
        try:
            with httpx.Client(timeout=25, trust_env=False) as client:
                result = client.request(method, proxy_url + '/providers', json=payload,
                                        headers={'Authorization': f'Bearer {token}'})
        except httpx.HTTPError:
            raise ApiError('GATEWAY_UNAVAILABLE', '本地模型代理尚未启动，请重启测试服务') from None
        try:
            data = result.json()
        except ValueError:
            raise ApiError('GATEWAY_UNAVAILABLE', '本地模型代理响应无效，请重启测试服务') from None
        return JSONResponse(data, status_code=result.status_code, headers={'Cache-Control': 'no-store'})

    @app.get('/api/v2/local-providers', dependencies=[Depends(gate)], include_in_schema=False)
    def providers():
        return forward('GET')

    @app.post('/api/v2/local-providers', dependencies=[Depends(gate)], include_in_schema=False)
    def add(payload: ProviderInput):
        return forward('POST', payload.model_dump() | {'apiKey': payload.apiKey.get_secret_value()})


def factory():
    return create_proxy(os.environ['LEARN_LOCAL_PROXY_TOKEN'])
