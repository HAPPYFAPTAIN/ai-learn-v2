"""模型网关客户端。

网关是官网那套 OpenAI 兼容服务。这里多做三件事：

1. 每次调用先拿租约，避免单租户把并发吃满；
2. 事件 id 由调用方给，后台任务只重试确认未发送或明确限流的请求；
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
UNKNOWN_RESULT = "模型请求结果未确认，已停止自动重试。请核对任务与用量记录"


class GatewayError(RuntimeError):
    def __init__(self, status: int, message: str, *, retryable: bool = False, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.code = code or ("INSUFFICIENT_CREDITS" if status == 402 else
                             "RESULT_UNCONFIRMED" if status >= 500 or status == 409 else
                             "GATEWAY_REJECTED" if status >= 400 else "GATEWAY_UNAVAILABLE")


@dataclass
class ChatResult:
    content: str
    model: str
    usage: dict[str, Any]
    truncated: bool = False


class GatewayClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        product_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._key = product_key if product_key is not None else settings.gateway_product_key
        read_timeout = settings.gateway_read_timeout if timeout is None else timeout
        self._detached_lease_ttl = timedelta(seconds=max(300, read_timeout + 60))
        self._client = httpx.Client(
            base_url=(base_url or settings.gateway_url).rstrip("/"),
            timeout=httpx.Timeout(read_timeout, connect=5, write=10, pool=5),
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

        The caller must close its input transaction first. Each invocation makes
        one HTTP attempt; the task runner decides whether to retry.
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
            credential = None
            if get_settings().model_source == 'personal' or selected.startswith('personal.'):
                from learn_core.llm.providers import resolve, ProviderError
                try:
                    credential = resolve(session, selected)
                except ProviderError as exc:
                    raise GatewayError(422, str(exc)) from None
            holder = acquire(session, tenant_id=tenant_id, lane=lane, ttl=self._detached_lease_ttl)

        payload: dict[str, Any] = {"messages": list(messages), "model": selected, **params}
        actual_model = credential.model if credential else selected
        if "kimi" in actual_model.lower():
            payload.pop("temperature", None)
            payload.pop("top_p", None)
        if "deepseek" in actual_model.lower():
            payload["reasoning_effort"] = "low"
        result = None
        status = "transport_error"
        usage: dict = {}
        try:
            try:
                if credential:
                    from learn_core.llm.providers import call, ProviderError
                    try:
                        response = call(credential, 'POST', '/chat/completions',
                                        payload={**payload, 'model': credential.model},
                                        timeout=get_settings().gateway_read_timeout)
                    except ProviderError as exc:
                        raise GatewayError(422, str(exc)) from None
                else:
                    response = self._client.post(
                        "/chat/completions", json=payload,
                        headers={"Authorization": f"Bearer {self._key}",
                                 "X-Event-Id": event_id, "X-End-User": end_user,
                                 "X-Product": "learn-everything"},
                    )
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                status = "connect_error"
                raise GatewayError(0, "无法连接模型网关，请稍后重试", retryable=True) from exc
            except httpx.ReadTimeout as exc:
                status = "read_timeout"
                raise GatewayError(504, f"等待模型响应超时。{UNKNOWN_RESULT}") from exc
            except httpx.TransportError as exc:
                raise GatewayError(502, f"模型请求传输中断。{UNKNOWN_RESULT}") from exc
            status = f"http_{response.status_code}"
            if response.status_code >= 400:
                # Upstream bodies can contain credentials or internal URLs.
                code = response.status_code
                if credential and code in {401, 403}:
                    raise GatewayError(422, "API Key 无效或权限已变更，请在模型设置中移除后重新导入。")
                if code == 402:
                    raise GatewayError(code, "官网积分不足，请充值后重试")
                if code == 409:
                    raise GatewayError(code, UNKNOWN_RESULT)
                if code == 429:
                    raise GatewayError(code, "模型网关限流，请稍后重试（HTTP 429）", retryable=True)
                if code == 504:
                    raise GatewayError(code, f"模型网关等待上游响应超时（HTTP 504）。{UNKNOWN_RESULT}")
                if code >= 500:
                    raise GatewayError(code, f"模型网关暂时不可用（HTTP {code}）。{UNKNOWN_RESULT}")
                raise GatewayError(code, f"模型网关拒绝请求（HTTP {code}）")
            status = "invalid_output"
            try:
                data = response.json()
                choice = data["choices"][0]
                content = choice["message"].get("content")
                usage = data.get("usage") or {}
                if not isinstance(usage, dict):
                    usage = {}
                truncated = choice.get("finish_reason") == "length"
                if not isinstance(content, str) or not content.strip():
                    if truncated:
                        raise GatewayError(422, '生成内容超出长度上限，未能保存。可以缩小章节范围后重试。', code='OUTPUT_TRUNCATED')
                    raise ValueError("empty content")
                result = ChatResult(content=content, model=selected if credential else str(data.get("model") or selected), usage=usage, truncated=truncated)
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise GatewayError(422, "模型网关返回了无效内容") from exc
            status = "truncated" if result.truncated else "ok"
            return result
        finally:
            with session_scope() as session:
                session.add(ModelCall(event_id=event_id, job_id=job_id, purpose=purpose,
                                      model=result.model if result else selected, status=status,
                                      usage=usage))
                release(session, tenant_id=tenant_id, lane=lane, holder=holder)
