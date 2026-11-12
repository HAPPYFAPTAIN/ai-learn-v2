"""身份解析。

生产路径：nginx 注入内部密钥 + 官网签发的短票，API 再向官网复核一次，
拿到 ``official_user_id``。复核失败一律当未登录，不做本地降级。
测试路径：直接覆盖 ``get_principal`` 依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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
    """向官网鉴权接口复核短票。"""

    def __init__(self, url: str | None = None, internal_secret: str | None = None) -> None:
        settings = get_settings()
        self._url = url or settings.authorize_url
        self._secret = internal_secret or settings.internal_secret

    def verify(self, ticket: str) -> Principal:
        try:
            response = httpx.post(
                self._url,
                json={"ticket": ticket, "product": "learn-everything"},
                headers={"X-Internal-Secret": self._secret},
                timeout=5.0,
            )
        except httpx.HTTPError as exc:
            raise ApiError("INTERNAL", f"authorize unreachable: {exc.__class__.__name__}") from exc

        if response.status_code in (401, 403):
            raise ApiError("UNAUTHENTICATED", "ticket rejected")
        if response.status_code >= 400:
            raise ApiError("INTERNAL", f"authorize returned {response.status_code}")

        data = response.json()
        user_id = data.get("official_user_id") or data.get("userId")
        if not user_id:
            raise ApiError("UNAUTHENTICATED", "authorize returned no user")
        return Principal(
            official_user_id=str(user_id),
            display_name=str(data.get("display_name") or ""),
            ticket=ticket,
        )


class DevTicketVerifier:
    """只在本地演示用：任何非空 ticket 都会变成一个独立租户。

    生产环境绝不能用——它不做任何身份校验。只有显式设置
    ``LEARN_DEV_AUTH=1`` 时才会被装上。
    """

    def verify(self, ticket: str) -> Principal:
        return Principal(official_user_id=f"dev-{ticket}", display_name=ticket, ticket=ticket)


def _default_verifier() -> TicketVerifier:
    import os

    if os.getenv("LEARN_DEV_AUTH") == "1":
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
    return _verifier.verify(extract_ticket(request))
