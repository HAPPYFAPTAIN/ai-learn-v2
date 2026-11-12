"""模型网关客户端。

网关是官网那套 OpenAI 兼容服务。这里多做三件事：

1. 每次调用先拿租约，避免单租户把并发吃满；
2. 事件 id 由调用方给，传输失败用同一个 id 重发，业务重试用新 id；
3. 每次调用写一行 ``model_call``，和网关账单逐条对账。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from learn_core.config import get_settings
from learn_core.db.models import ModelCall
from learn_core.llm.lease import lease

LANE_BY_PURPOSE = {"interactive": "interactive", "background": "background"}


class GatewayError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class ChatResult:
    content: str
    model: str
    usage: dict[str, Any]


class GatewayClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        product_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
    ) -> None:
        settings = get_settings()
        self._key = product_key if product_key is not None else settings.gateway_product_key
        self._client = httpx.Client(
            base_url=(base_url or settings.gateway_url).rstrip("/"),
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GatewayClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def chat(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        event_id: str,
        messages: Sequence[dict[str, str]],
        purpose: str = "",
        model: str = "",
        background: bool = False,
        **params: Any,
    ) -> ChatResult:
        lane = "background" if background else "interactive"
        payload: dict[str, Any] = {"messages": list(messages), **params}
        if model:
            payload["model"] = model

        with lease(session, tenant_id=tenant_id, lane=lane):
            try:
                response = self._client.post(
                    "/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._key}",
                        "X-Event-Id": event_id,
                        "X-Product": "learn-everything",
                    },
                )
            except httpx.HTTPError as exc:
                self._record(session, event_id, purpose, model, "transport_error", {})
                raise GatewayError(0, f"gateway unreachable: {exc.__class__.__name__}") from exc

            if response.status_code >= 400:
                self._record(session, event_id, purpose, model, f"http_{response.status_code}", {})
                raise GatewayError(response.status_code, response.text[:300])

            data = response.json()
            content = data["choices"][0]["message"].get("content") or ""
            usage = data.get("usage") or {}
            self._record(session, event_id, purpose, data.get("model", model), "ok", usage)
            return ChatResult(content=content, model=data.get("model", model), usage=usage)

    @staticmethod
    def _record(
        session: Session,
        event_id: str,
        purpose: str,
        model: str,
        status: str,
        usage: dict[str, Any],
    ) -> None:
        session.add(
            ModelCall(
                event_id=event_id,
                purpose=purpose[:64],
                model=(model or "")[:128],
                status=status[:16],
                usage=usage,
            )
        )
        session.flush()
