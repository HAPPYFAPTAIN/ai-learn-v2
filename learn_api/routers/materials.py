"""Account-shared library: upload/index, text preview, download and deletion."""
from pathlib import Path
from urllib.parse import quote
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from learn_api.deps import get_session
from learn_api.errors import ApiError
from learn_api.schemas import Items, MaterialOut, UploadOut, MaterialPreviewOut, GenerationOut
from learn_core.db.models import StoredFile
from learn_core.learning import projects as project_service, materials as service
from learn_core.storage import files as storage
from learn_core.storage.parsing import EXTENSIONS

router = APIRouter(tags=['materials'])
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _file(session, file_id):
    row = session.get(StoredFile, file_id)
    if row is None or row.kind != 'material':
        raise ApiError('NOT_FOUND', '资料不存在或已删除')
    return row


@router.post('/projects/{project_id}/materials', status_code=status.HTTP_202_ACCEPTED, response_model=UploadOut)
async def upload_material(project_id: int, response: Response, file: UploadFile = File(...),
                          index: bool = Form(default=True), session: Session = Depends(get_session)):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ApiError('INVALID_ARGUMENT', '请选择非空且不超过 50 MB 的文件')
    name = Path((file.filename or '').replace('\\','/')).name
    if len(name) > 255 or Path(name).suffix.lower() not in EXTENSIONS:
        raise ApiError('INVALID_ARGUMENT', '当前支持 TXT、Markdown、PDF 和 DOCX 文件，文件名不超过 255 字符')
    if project_service.get_project(session, project_id) is None:
        raise ApiError('NOT_FOUND', '学习计划不存在')
    try:
        row, job = service.upload(session, data=data, name=name, index=index)
    except OverflowError as exc:
        raise ApiError('STORAGE_FULL', str(exc)) from exc
    if job:
        response.headers['Location'] = f'/official/learn-everything/api/v2/jobs/{job.job_id}'
    return {'fileId':str(row.id), 'sha256':row.sha256, 'sizeBytes':row.size_bytes, 'jobId':job.job_id if job else None}


@router.get('/projects/{project_id}/materials', response_model=Items[MaterialOut])
def list_materials(project_id: int, session: Session = Depends(get_session)):
    if project_service.get_project(session, project_id) is None:
        raise ApiError('NOT_FOUND', '学习计划不存在')
    rows = session.scalars(select(StoredFile).where(StoredFile.kind == 'material').order_by(StoredFile.created_at.desc()))
    return {'items':[{'fileId':str(r.id), 'name':r.original_name, 'sizeBytes':r.size_bytes, 'sha256':r.sha256, 'createdAt':r.created_at} for r in rows]}


@router.get('/materials/{file_id}/preview', response_model=MaterialPreviewOut)
def preview(file_id: UUID, response: Response, session: Session = Depends(get_session)):
    row = _file(session, file_id)
    response.headers['Cache-Control'] = 'no-store'
    chunks = list(session.scalars(text("SELECT text FROM rag_chunk WHERE index_id='material' AND source_id=:id ORDER BY split_part(chunk_id, ':', 2)::int LIMIT 101"), {'id':str(file_id)}))
    if not chunks:
        raise ApiError('INVALID_ARGUMENT', '资料尚未完成索引，请稍后查看，或点击重新索引')
    return {'fileId':str(row.id), 'name':row.original_name, 'text':'\n\n'.join(chunks[:100]), 'truncated':len(chunks)>100}


@router.get('/materials/{file_id}/download')
def download(file_id: UUID, session: Session = Depends(get_session)):
    row = _file(session, file_id)
    try:
        source = storage.open_file(row.storage_key)
    except FileNotFoundError as exc:
        raise ApiError('NOT_FOUND', '资料原件暂不可用，请重新上传') from exc
    def chunks():
        with source:
            while chunk := source.read(65536):
                yield chunk
    return StreamingResponse(chunks(), media_type='application/octet-stream', headers={
        'Content-Disposition':f"attachment; filename*=UTF-8''{quote(row.original_name, safe='')}",
        'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
    })


@router.post('/materials/{file_id}/index', response_model=GenerationOut, status_code=202)
def reindex(file_id: UUID, session: Session = Depends(get_session)):
    service.storage_lock(session)
    job = service.schedule_index(session, row=_file(session, file_id))
    return {'jobId':job.job_id, 'state':job.state}


@router.delete('/materials/{file_id}', status_code=204)
def delete(file_id: UUID, session: Session = Depends(get_session)):
    service.storage_lock(session)
    service.remove(session, row=_file(session, file_id))
    return Response(status_code=204)
