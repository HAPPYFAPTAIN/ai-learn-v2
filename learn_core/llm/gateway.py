"""模型网关客户端。

网关是官网那套 OpenAI 兼容服务。这里多做三件事：

1. 每次调用先拿租约，避免单租户把并发吃满；
2. 事件 id 由调用方给，传输失败用同一个 id 重发，业务重试用新 id；
3. 每次调用写一行 ``model_call``，和网关账单逐条对账。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Sequence
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from learn_core.config import get_settings
from learn_core.db.models import ModelCall, Tenant, TenantSetting
from learn_core.db.engine import session_scope
from learn_core.tenancy.context import current_tenant
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

    def list_models(self, *, end_user: str) -> list[dict[str, str]]:
        """Ask the official gateway for this verified user's catalog. No paid call."""
        try:
            response = self._client.get('/models', timeout=10.0, headers={
                'Authorization': f'Bearer {self._key}',
                'X-End-User': end_user, 'X-Product': 'learn-everything',
            })
        except httpx.HTTPError as exc:
            raise GatewayError(0, '暂时无法读取可用模型，请稍后重试') from exc
        if response.status_code >= 400:
            raise GatewayError(response.status_code, '暂时无法读取可用模型，请稍后重试')
        try:
            rows = response.json()['data']
            if not isinstance(rows, list) or len(rows) > 2000:
                raise ValueError('invalid catalog')
            models = {}
            for row in rows:
                mid = row['id']
                if not isinstance(mid, str) or not mid.strip() or len(mid) > 128:
                    raise ValueError('invalid model id')
                owner = row.get('owned_by', '')
                models[mid] = {'id': mid, 'provider': owner[:128] if isinstance(owner, str) else ''}
            return [models[mid] for mid in sorted(models)]
        except (KeyError, TypeError, ValueError) as exc:
            raise GatewayError(422, '模型列表格式无效，请稍后重试') from exc

    def chat_detached(
        self, *, event_id: str, job_id: str, messages: Sequence[dict[str, str]],
        purpose: str, model: str = "", lane: str = "background", **params: Any,
    ) -> ChatResult:
        """Worker calls: commit the lease before HTTP; record/release in a new transaction.

        The caller must close its input transaction first. Transport retry reuses
        exactly the same body and event id; task retry supplies a new event id.
        """
        from learn_core.llm.lease import acquire, release

        tenant_id = current_tenant()
        with session_scope() as session:
            tenant = session.get(Tenant, tenant_id)
            if tenant is None or tenant.status != "active":
                raise GatewayError(403, "学习账号不可用")
            end_user = tenant.official_user_id
            setting = session.get(TenantSetting, tenant_id)
            selected = model or (setting.chat_model if setting else "")
            if not selected:
                raise GatewayError(400, "尚未配置网关主模型")
            holder = acquire(session, tenant_id=tenant_id, lane=lane, ttl=timedelta(minutes=5))

        payload: dict[str, Any] = {"messages": list(messages), "model": selected, **params}
        if "kimi" in selected.lower():
            payload.pop("temperature", None)
            payload.pop("top_p", None)
        if "deepseek" in selected.lower():
            payload["reasoning_effort"] = "low"
        result = None
        status = "transport_error"
        usage: dict = {}
        try:
            for attempt in range(2):
                try:
                    response = self._client.post(
                        "/chat/completions", json=payload,
                        headers={"Authorization": f"Bearer {self._key}",
                                 "X-Event-Id": event_id, "X-End-User": end_user,
                                 "X-Product": "learn-everything"},
                    )
                    break
                except httpx.TransportError as exc:
                    if attempt:
                        raise GatewayError(0, "模型网关连接失败或超时") from exc
            status = f"http_{response.status_code}"
            if response.status_code >= 400:
                # Upstream bodies can contain credentials or internal URLs.
                raise GatewayError(response.status_code, f"模型网关返回 HTTP {response.status_code}")
            status = "invalid_output"
            try:
                data = response.json()
                choice = data["choices"][0]
                content = choice["message"].get("content")
                usage = data.get("usage") or {}
                if not isinstance(usage, dict):
                    usage = {}
                if choice.get("finish_reason") == "length":
                    raise GatewayError(422, "模型输出被截断，请调整模型输出限制后重试")
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("empty content")
                result = ChatResult(content=content, model=str(data.get("model") or selected), usage=usage)
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise GatewayError(422, "模型网关返回了无效内容") from exc
            status = "ok"
            return result
        finally:
            with session_scope() as session:
                session.add(ModelCall(event_id=event_id, job_id=job_id, purpose=purpose,
                                      model=result.model if result else selected, status=status,
                                      usage=usage))
                release(session, tenant_id=tenant_id, lane=lane, holder=holder)

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
