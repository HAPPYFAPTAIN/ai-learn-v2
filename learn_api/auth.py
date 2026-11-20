"""身份解析。

生产路径：nginx 注入内部密钥 + 官网签发的短票，API 再向官网复核一次，
拿到 ``official_user_id``。复核失败一律当未登录，不做本地降级。
测试路径：直接覆盖 ``get_principal`` 依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from hmac import compare_digest
from http.cookies import SimpleCookie
import re
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from fastapi import Request

from learn_api.errors import ApiError
from learn_core.config import get_settings


@dataclass(frozen=True)
class Principal:
    official_user_id: str
    display_name: str = ""
    # 短票在请求内有效；用于调用网关时透传。
    ticket: str = ""


class TicketVerifier(Protocol):
    def verify(self, ticket: str) -> Principal: ...


class HttpTicketVerifier:
    """Reuse the existing official GET/204/header protocol, never client identity headers."""

    def __init__(self, url: str | None = None, internal_secret: str | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        settings = get_settings()
        self._url = url or settings.authorize_url
        self._secret = internal_secret if internal_secret is not None else settings.internal_secret
        self._transport = transport

    def verify(self, ticket: str) -> Principal:
        return self._authorize(ticket)[0]

    def _authorize(self, ticket: str) -> tuple[Principal, str]:
        cookie = SimpleCookie()
        cookie['learn_entry'] = ticket
        try:
            with httpx.Client(timeout=5.0, transport=self._transport, follow_redirects=False) as client:
                response = client.get(self._url, headers={
                    'Cookie':cookie.output(header='').strip(),
                    'X-Original-URI':'/official/learn-everything/',
                })
        except httpx.HTTPError as exc:
            raise ApiError('GATEWAY_UNAVAILABLE', '官网登录验证暂不可用，请稍后重试') from exc

        if response.status_code == 401:
            raise ApiError('UNAUTHENTICATED', '登录已过期，请从官网重新进入')
        if response.status_code == 403:
            raise ApiError('ENTITLEMENT_REQUIRED', '请从官网确认登录及学习产品使用资格')
        if response.status_code != 204:
            raise ApiError('GATEWAY_UNAVAILABLE', '官网登录验证暂不可用，请稍后重试')

        user_id = response.headers.get('X-Learn-User', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', user_id):
            raise ApiError('UNAUTHENTICATED', '官网未返回有效学习账号')
        renewed = response.headers.get('X-Learn-Entry-Cookie', '')
        # Forward only the expected cookie from the trusted authorize endpoint.
        if renewed and (not renewed.startswith('learn_entry=') or '\r' in renewed or '\n' in renewed):
            raise ApiError('GATEWAY_UNAVAILABLE', '官网登录续期响应无效')
        return Principal(official_user_id=user_id, ticket=ticket), renewed

    def verify_request(self, request: Request) -> tuple[Principal, str]:
        if len(self._secret) < 32:
            raise ApiError('INTERNAL', '学习服务尚未配置可信入口')
        supplied = request.headers.get('X-Learn-Internal-Secret', '')
        if not compare_digest(supplied.encode(), self._secret.encode()):
            raise ApiError('UNAUTHENTICATED', '请从官网进入学习工作台')
        if request.method not in {'GET','HEAD','OPTIONS'}:
            settings = get_settings()
            origin = settings.public_origin
            parsed = urlsplit(origin)
            if parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.path not in {'','/'} or parsed.query or parsed.fragment or parsed.username:
                raise ApiError('INTERNAL', '学习服务尚未配置公开站点地址')
            if (request.headers.get('Origin') is not None and request.headers['Origin'] != origin.rstrip('/')) or request.headers.get('Sec-Fetch-Site') in {'cross-site','same-site'}:
                raise ApiError('ENTITLEMENT_REQUIRED', '请从当前学习工作台操作')
        ticket = request.cookies.get('learn_entry')
        if not ticket:
            raise ApiError('UNAUTHENTICATED', '登录已过期，请从官网重新进入')
        return self._authorize(ticket)


class DevTicketVerifier:
    """只在本地演示用：任何非空 ticket 都会变成一个独立租户。

    生产环境绝不能用——它不做任何身份校验。只有显式设置
    ``LEARN_DEV_AUTH=1`` 时才会被装上。
    """

    def verify(self, ticket: str) -> Principal:
        return Principal(official_user_id=f"dev-{ticket}", display_name=ticket, ticket=ticket)


def validate_dev_auth() -> None:
    import os
    if os.getenv('LEARN_DEV_AUTH') != '1':
        return
    origin = urlsplit(get_settings().public_origin)
    if (origin.scheme != 'http' or origin.hostname not in {'127.0.0.1', 'localhost'}
            or origin.username or origin.password or origin.path not in {'', '/'}
            or origin.query or origin.fragment):
        raise RuntimeError('LEARN_DEV_AUTH 仅允许 HTTP 本地回环地址')


def _default_verifier() -> TicketVerifier:
    import os

    if os.getenv("LEARN_DEV_AUTH") == "1":
        validate_dev_auth()
        return DevTicketVerifier()
    return HttpTicketVerifier()


_verifier: TicketVerifier = _default_verifier()


def set_verifier(verifier: TicketVerifier) -> None:
    """测试与本地联调用的替换入口。"""
    global _verifier
    _verifier = verifier


def extract_ticket(request: Request) -> str:
    ticket = request.headers.get("X-Learn-Ticket") or request.cookies.get("le_ticket")
    if not ticket:
        raise ApiError("UNAUTHENTICATED", "missing ticket")
    return ticket


def get_principal(request: Request) -> Principal:
    official = isinstance(_verifier, HttpTicketVerifier)
    principal, renewed = _verifier.verify_request(request) if official else (_verifier.verify(extract_ticket(request)), '')
    expected = request.headers.get("X-Learn-Expected-User") or request.query_params.get("__le_owner")
    if (expected and expected != principal.official_user_id) or (official and request.url.path != '/api/v2/me' and not expected):
        raise ApiError("ACCOUNT_CHANGED", "account changed; reopen from the official website")
    if official and request.headers.get('X-Learn-User', principal.official_user_id) != principal.official_user_id:
        raise ApiError('UNAUTHENTICATED', '工作空间身份不匹配')
    request.state.account_id = principal.official_user_id
    request.state.authorized_entry_cookie = renewed
    return principal
