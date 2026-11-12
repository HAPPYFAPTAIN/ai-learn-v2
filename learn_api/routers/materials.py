"""资料上传：落存储 → 建 stored_file → 派生索引任务。

上传和索引拆开：上传只要写完盘就能返回，索引在 io 通道排队，
这样大文件不会把 HTTP 请求拖住，失败也能单独重试。
"""

from __future__ import annotations

import io
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_api.deps import get_session, get_tenant_id
from learn_api.errors import ApiError
from learn_core.db.models import JobProgress, StoredFile as StoredFileRow
from learn_core.jobs import enqueue
from learn_core.learning import projects as project_service
from learn_core.storage import files as storage

router = APIRouter(prefix="/projects", tags=["materials"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/{project_id}/materials", status_code=status.HTTP_202_ACCEPTED)
async def upload_material(
    project_id: int,
    response: Response,
    file: UploadFile = File(...),
    index: bool = Form(default=True),
    tenant_id: UUID = Depends(get_tenant_id),
    session: Session = Depends(get_session),
) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError("INVALID_ARGUMENT", "file too large (max 50 MiB)")
    if not data:
        raise ApiError("INVALID_ARGUMENT", "empty file")

    saved = storage.put(io.BytesIO(data), kind="material", tenant_id=tenant_id)
    row = session.scalars(
        select(StoredFileRow).where(
            StoredFileRow.tenant_id == tenant_id, StoredFileRow.sha256 == saved.sha256
        )
    ).first()
    if row is None:
        row = StoredFileRow(
            id=uuid4(),
            kind="material",
            sha256=saved.sha256,
            size_bytes=saved.size_bytes,
            storage_key=saved.storage_key,
            original_name=(file.filename or "")[:255],
        )
        session.add(row)
        session.flush()

    job_id = None
    if index:
        job_id = f"idx-{uuid4().hex[:12]}"
        session.add(
            JobProgress(
                job_id=job_id,
                kind="index",
                subject=str(row.id),
                state="queued",
                progress={"done": 0, "total": 0},
            )
        )
        session.flush()
        text = data.decode("utf-8", errors="replace")
        try:
            enqueue.enqueue_index(
                tenant_id=tenant_id,
                job_id=job_id,
                source_id=str(row.id),
                text=text,
                index_id="material",
            )
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            raise ApiError("INTERNAL", f"queue unavailable: {exc.__class__.__name__}") from exc
        response.headers["Location"] = f"/official/learn-everything/api/v2/jobs/{job_id}"

    return {
        "fileId": str(row.id),
        "sha256": row.sha256,
        "sizeBytes": row.size_bytes,
        "jobId": job_id,
    }


@router.get("/{project_id}/materials")
def list_materials(project_id: int, session: Session = Depends(get_session)) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    rows = session.scalars(
        select(StoredFileRow).where(StoredFileRow.kind == "material").order_by(StoredFileRow.created_at.desc())
    )
    return {
        "items": [
            {
                "fileId": str(r.id),
                "name": r.original_name,
                "sizeBytes": r.size_bytes,
                "sha256": r.sha256,
                "createdAt": r.created_at,
            }
            for r in rows
        ]
    }
