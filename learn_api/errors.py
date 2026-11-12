"""API 错误码与统一响应体。

前端只认 ``error.code``，文案变化不影响它；``retryable`` 决定要不要
自动重试，``retryAfterSeconds`` 只在限流/忙时出现。
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

CODES: dict[str, tuple[int, bool]] = {
    "UNAUTHENTICATED": (401, False),
    "ENTITLEMENT_REQUIRED": (403, False),
    "INSUFFICIENT_CREDITS": (402, False),
    "NOT_FOUND": (404, False),
    "ACCOUNT_CHANGED": (409, False),
    "CONFLICT": (409, False),
    "JOB_RUNNING": (409, False),
    "TENANT_BUSY": (429, True),
    "STORAGE_FULL": (507, False),
    "INVALID_ARGUMENT": (422, False),
    "INTERNAL": (500, True),
}


@dataclass
class ApiError(Exception):
    code: str
    message: str = ""
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.code not in CODES:
            raise ValueError(f"unknown error code: {self.code}")
        if not self.message:
            self.message = self.code

    @property
    def status_code(self) -> int:
        return CODES[self.code][0]


def error_response(code: str, message: str, retry_after: int | None = None) -> JSONResponse:
    status, retryable = CODES[code]
    body = {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        }
    }
    headers = {}
    if retry_after is not None:
        body["error"]["retryAfterSeconds"] = retry_after
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(status_code=status, content=body, headers=headers)


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.code, exc.message, exc.retry_after_seconds)


async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    # 不在响应里暴露堆栈；日志由中间件记录 request id。
    return error_response("INTERNAL", "internal error")
