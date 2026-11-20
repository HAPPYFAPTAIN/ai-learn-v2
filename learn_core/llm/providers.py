"""Personal OpenAI-compatible connections. No keys in browser replies or jobs.

Only explicit imports fetch /models. Generation reuses the existing worker,
lease and retry rules; checked public IPs are pinned for each upstream request.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from learn_core.config import get_settings
from learn_core.db.models import ModelProvider, TenantSetting
from learn_core.tenancy.context import current_tenant


class ProviderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ModelNotConfigured(ProviderError):
    def __init__(self, code='MODEL_NOT_CONFIGURED', message='请先导入 API Key，并在模型设置中选择主模型。'):
        super().__init__(code, message)


class ProviderInput(BaseModel):
    id: str = Field(pattern=r'^[a-f0-9]{12}$')
    provider: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    baseUrl: str = Field(min_length=1, max_length=500)
    apiKey: SecretStr = Field(min_length=1, max_length=4096)
    models: list[str] = Field(min_length=1, max_length=100)
    remark: str = Field(default='', max_length=200)
    website: str = Field(default='', max_length=500)


def cipher():
    try:
        from cryptography.fernet import Fernet
        return Fernet(get_settings().provider_encryption_key.get_secret_value().encode())
    except (ImportError, ValueError, TypeError):
        raise ProviderError('PROVIDER_SETUP_REQUIRED', '服务器尚未配置个人 Key 加密存储，请联系管理员。') from None


def enabled() -> bool:
    try:
        cipher()
        return True
    except ProviderError:
        return False


def encrypt_key(value: str, cid: str) -> str:
    # Bind ciphertext to its tenant and connection; copying rows cannot swap keys.
    return cipher().encrypt(json.dumps([str(current_tenant()), cid, value]).encode()).decode()


def decrypt_key(value: str, cid: str) -> str:
    from cryptography.fernet import InvalidToken
    try:
        tid, stored_id, key = json.loads(cipher().decrypt(value.encode()))
        if tid != str(current_tenant()) or cid != stored_id:
            raise ValueError()
        return key
    except (InvalidToken, ValueError, TypeError):
        raise ProviderError('PROVIDER_SETUP_REQUIRED', '无法读取已保存的 Key，请检查服务器加密配置或重新导入。') from None


def public_target(value: str, path: str) -> tuple[str, str]:
    try:
        url = urlsplit(value)
        port = url.port
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment or port not in {None, 443}
                or any(ord(c) < 33 or ord(c) > 126 for c in value)):
            raise ValueError()
        addresses = socket.getaddrinfo(url.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValueError()
    except (OSError, ValueError):
        raise ProviderError('INVALID_ARGUMENT', '请使用可解析的公网 HTTPS API 地址（443 端口），不支持本机、内网或带密钥的地址。') from None
    address = addresses[0][4][0]
    authority = f'[{address}]' if ':' in address else address
    return urlunsplit(('https', authority, url.path.rstrip('/') + path, '', '')), url.hostname


@dataclass
class Credential:
    base_url: str
    key: str = field(repr=False)
    model: str = ''


def call(credential: Credential, method: str, path: str, *, payload=None, timeout=120, transport=None):
    target, host = public_target(credential.base_url, path)
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=5, write=10, pool=5),
                      follow_redirects=False, trust_env=False, transport=transport) as client:
        return client.request(method, target, json=payload,
                              headers={'Authorization': f'Bearer {credential.key}', 'Host': host},
                              extensions={'sni_hostname': host})


def verify(payload: ProviderInput, *, transport=None) -> None:
    cipher()  # Fail before sending credentials if persistence is not configured.
    ids = list(dict.fromkeys(m.strip() for m in payload.models))
    key = payload.apiKey.get_secret_value().strip()
    if (not key or any(ord(c) < 33 or ord(c) > 126 for c in key)
            or not payload.name.strip() or not ids
            or any(not m or len(m) > 100 or any(ord(c) < 32 for c in m) for m in ids)):
        raise ProviderError('INVALID_ARGUMENT', '请检查供应商名称、Key 和模型 ID（每个最多 100 字符）。')
    try:
        response = call(Credential(payload.baseUrl.strip(), key), 'GET', '/models', timeout=15, transport=transport)
    except httpx.HTTPError:
        raise ProviderError('PROVIDER_UNAVAILABLE', '无法连接供应商，请检查 API 地址和网络。') from None
    if response.status_code in {401, 403}:
        raise ProviderError('PROVIDER_KEY_INVALID', 'API Key 无效或没有访问权限，请检查后重新导入。')
    if response.status_code != 200:
        raise ProviderError('INVALID_ARGUMENT', f'供应商返回 HTTP {response.status_code}，请检查额度和接口兼容性。')
    try:
        rows = response.json()['data']
        if not isinstance(rows, list) or len(rows) > 2000:
            raise ValueError()
        available = {row['id'] for row in rows if isinstance(row, dict) and isinstance(row.get('id'), str)}
        if any(mid not in available for mid in ids):
            raise ProviderError('INVALID_ARGUMENT', '部分模型 ID 不在供应商返回的目录中，请填写当前 Key 可用的模型 ID。')
    except (ValueError, TypeError, KeyError):
        raise ProviderError('INVALID_ARGUMENT', '供应商需要兼容 OpenAI 的 /models 和 /chat/completions 接口。') from None


def connections(session: Session) -> list[dict]:
    return [row.metadata_json for row in session.scalars(select(ModelProvider).order_by(ModelProvider.created_at))]


def lock_connections(session: Session) -> None:
    session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': f'{current_tenant()}:providers'})


def save(session: Session, *, payload: ProviderInput) -> dict:
    # Serialize modifications per tenant, including the size limit and retries.
    lock_connections(session)
    existing = session.get(ModelProvider, payload.id)
    if existing:
        # A lost HTTP response may be retried using the same ID, never duplicated.
        if (existing.name != payload.name.strip() or existing.metadata_json['baseUrl'] != payload.baseUrl.strip().rstrip('/')
                or [m.split('.', 2)[2] for m in existing.metadata_json['models']] != list(dict.fromkeys(m.strip() for m in payload.models))
                or decrypt_key(existing.encrypted_key, existing.id) != payload.apiKey.get_secret_value().strip()):
            raise ProviderError('INVALID_ARGUMENT', '本次导入编号已使用，请关闭弹窗后重新添加。')
        return existing.metadata_json
    rows = list(session.scalars(select(ModelProvider)))
    if len(rows) >= 20:
        raise ProviderError('INVALID_ARGUMENT', '每个账号最多保存 20 个供应商，请先移除不用的供应商。')
    if any(row.name == payload.name.strip() for row in rows):
        raise ProviderError('INVALID_ARGUMENT', '供应商名称已存在，请使用不同名称。')
    metadata = payload.model_dump(exclude={'apiKey'})
    metadata.update(name=payload.name.strip(), baseUrl=payload.baseUrl.strip().rstrip('/'),
                    models=[f'personal.{payload.id}.{mid}' for mid in dict.fromkeys(m.strip() for m in payload.models)])
    row = ModelProvider(id=payload.id, name=payload.name.strip(), metadata_json=metadata,
                        encrypted_key=encrypt_key(payload.apiKey.get_secret_value().strip(), payload.id))
    session.add(row)
    session.flush()
    return metadata


def resolve(session: Session, model: str) -> Credential:
    match = re.fullmatch(r'personal\.([a-f0-9]{12})\.(.+)', model)
    if not match:
        raise ModelNotConfigured()
    row = session.get(ModelProvider, match[1])
    if row is None or model not in row.metadata_json['models']:
        raise ModelNotConfigured()
    return Credential(row.metadata_json['baseUrl'], decrypt_key(row.encrypted_key, row.id), match[2])


def remove(session: Session, cid: str) -> None:
    lock_connections(session)
    row = session.get(ModelProvider, cid)
    if row is None:
        raise ProviderError('NOT_FOUND', '供应商不存在或已移除。')
    setting = session.get(TenantSetting, current_tenant())
    if setting and setting.chat_model in row.metadata_json['models']:
        setting.chat_model = ''
    session.delete(row)


def catalog(session: Session) -> list[dict]:
    return [{'id': mid, 'provider': c['id']} for c in connections(session) for mid in c['models']]
