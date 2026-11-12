"""文件存储：所有路径都由这里解析。

布局：{files_root}/{tenant_id}/{kind}/{sha256}
- 租户目录进去之前先取 TenantContext，没有租户直接报错；
- 只接受相对路径，拒绝绝对路径、`..` 和符号链接；
- 不跨租户按哈希去重，避免用哈希探测别人是否传过某个文件。
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator
from uuid import UUID

from learn_core.config import get_settings
from learn_core.tenancy.context import current_tenant

KINDS = {"material", "preview", "workspace", "export", "cache"}


class StoragePathError(ValueError):
    """路径不合法：绝对路径、越界或符号链接。"""


@dataclass(frozen=True)
class StoredFile:
    id: UUID | None
    tenant_id: UUID
    kind: str
    sha256: str
    size_bytes: int
    storage_key: str


def _root() -> Path:
    return Path(get_settings().files_root)


def tenant_dir(tenant_id: UUID | None = None) -> Path:
    tid = tenant_id or current_tenant()
    return _root() / str(tid)


def _kind_dir(kind: str, tenant_id: UUID | None = None) -> Path:
    if kind not in KINDS:
        raise StoragePathError(f"unknown kind: {kind}")
    path = tenant_dir(tenant_id) / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_workspace_path(relative: str, *, must_exist: bool = False) -> Path:
    """把网页工具传来的相对路径解析成租户工作区里的真实路径。"""
    if not relative or relative.startswith(("/", "~", "\\")):
        raise StoragePathError("absolute paths are not allowed")
    if "\x00" in relative:
        raise StoragePathError("null byte in path")

    workspace = _kind_dir("workspace")
    candidate = (workspace / relative).resolve()
    workspace_real = workspace.resolve()
    if not candidate.is_relative_to(workspace_real):
        raise StoragePathError("path escapes the tenant workspace")
    if candidate.is_symlink():
        raise StoragePathError("symlinks are not allowed")
    if must_exist and not candidate.exists():
        raise FileNotFoundError(relative)
    return candidate


def put(stream: BinaryIO, kind: str, tenant_id: UUID | None = None) -> StoredFile:
    """按内容哈希写入；同一租户同一内容只存一份。"""
    tid = tenant_id or current_tenant()
    digest = hashlib.sha256()
    target_dir = _kind_dir(kind, tid)
    tmp_path = target_dir / f".tmp-{os.getpid()}"
    size = 0
    with tmp_path.open("wb") as out:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            out.write(chunk)
    sha = digest.hexdigest()
    final_path = target_dir / sha
    if final_path.exists():
        tmp_path.unlink(missing_ok=True)
    else:
        os.replace(tmp_path, final_path)
    return StoredFile(
        id=None,
        tenant_id=tid,
        kind=kind,
        sha256=sha,
        size_bytes=size,
        storage_key=f"{tid}/{kind}/{sha}",
    )


def open_file(storage_key: str) -> BinaryIO:
    path = _safe_key_path(storage_key)
    return path.open("rb")


def delete(storage_key: str) -> None:
    path = _safe_key_path(storage_key)
    path.unlink(missing_ok=True)


def _safe_key_path(storage_key: str) -> Path:
    """storage_key 形如 {tenant}/{kind}/{sha256}，必须落在当前租户目录内。"""
    tid = current_tenant()
    parts = Path(storage_key).parts
    if len(parts) != 3 or parts[0] != str(tid):
        raise StoragePathError("storage key does not belong to the current tenant")
    if parts[1] not in KINDS:
        raise StoragePathError(f"unknown kind: {parts[1]}")
    path = (_root() / parts[0] / parts[1] / parts[2]).resolve()
    if not path.is_relative_to((tenant_dir(tid)).resolve()):
        raise StoragePathError("storage key escapes the tenant directory")
    return path


def iter_tenant_files(kind: str | None = None) -> Iterator[Path]:
    base = tenant_dir()
    roots = [base / kind] if kind else [base / k for k in KINDS]
    for root in roots:
        if not root.exists():
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                yield Path(dirpath) / name


def tenant_usage_bytes() -> int:
    return sum(p.stat().st_size for p in iter_tenant_files() if p.is_file())


def delete_tenant_files(tenant_id: UUID) -> None:
    """注销租户时调用；显式传 id，避免依赖上下文。"""
    shutil.rmtree(tenant_dir(tenant_id), ignore_errors=True)
