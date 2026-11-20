"""Library parsing, RLS access, quota, atomic queueing and delete/index races."""
import io
from pathlib import Path
from zipfile import ZipFile
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from learn_api.app import create_app
from learn_api.deps import get_tenant_id
from learn_core.config import get_settings
from learn_core.db.engine import session_scope, get_engine
from learn_core.db.models import StoredFile, Tenant, JobProgress
from learn_core.tenancy.context import tenant_context
from learn_core.learning import materials
from learn_core.storage import files as storage
from learn_core.storage.parsing import extract_text
from learn_core.jobs.tasks import index_material_task, purge_material_task
from tests.learn_core.test_generation import tenant, db_test


def docx(data):
    stream = io.BytesIO()
    with ZipFile(stream, 'w') as z:
        z.writestr('word/document.xml', data)
    return stream.getvalue()


def test_parses_actual_pdf_docx_and_utf8_without_binary_decoding():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
    pdf = PdfWriter()
    page = pdf.add_blank_page(width=200, height=200)
    font = DictionaryObject({NameObject('/Type'):NameObject('/Font'), NameObject('/Subtype'):NameObject('/Type1'), NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'):pdf._add_object(font)})})
    stream = DecodedStreamObject(); stream.set_data(b'BT /F1 12 Tf 20 150 Td (Learning from documents) Tj ET')
    page[NameObject('/Contents')] = pdf._add_object(stream)
    buffer = io.BytesIO(); pdf.write(buffer)
    assert 'Learning from documents' in extract_text(buffer.getvalue(), 'course.pdf')
    assert extract_text(docx('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>课程内容</w:t></w:r></w:p></w:body></w:document>'.encode()), 'course.docx') == '课程内容'
    assert extract_text('你好'.encode('utf-8-sig'), 'course.md') == '你好'
    for data, name in [(b'%PDF-broken','bad.pdf'), (b'not-zip','bad.docx'), (b'\xff','bad.txt'), (b'','empty.md')]:
        with pytest.raises(ValueError): extract_text(data,name)


@pytest.fixture
def library(tenant, tmp_path, monkeypatch):
    monkeypatch.setenv('LEARN_FILES_ROOT', str(tmp_path))
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as client:
        yield client, app
    get_settings.cache_clear()


def fake_embed(monkeypatch, callback=None):
    class Embedder:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def embed(self, chunks):
            assert get_engine().pool.checkedout() == 0
            if callback: callback()
            return [[1.0] + [0.0]*383 for _ in chunks]
    monkeypatch.setattr('learn_core.rag.embedding.EmbeddingClient', Embedder)


@db_test
def test_upload_preview_download_reindex_delete_and_cross_account_access(tenant, library, monkeypatch):
    client, app = library
    data = '课程解释变量的命名与数据保存。'.encode()
    result = client.post(f'/api/v2/projects/{tenant[1]}/materials', files={'file':('课程.md',data)}).json()
    fid, jid = result['fileId'], result['jobId']
    assert client.post(f'/api/v2/materials/{fid}/index').json()['jobId'] == jid
    fake_embed(monkeypatch)
    index_material_task(tenant=str(tenant[0]), job_id=jid, file_id=fid)
    preview = client.get(f'/api/v2/materials/{fid}/preview')
    assert preview.status_code == 200 and '变量' in preview.json()['text']
    download = client.get(f'/api/v2/materials/{fid}/download')
    assert download.content == data and download.headers['x-content-type-options'] == 'nosniff'
    assert 'filename*=UTF-8' in download.headers['content-disposition']
    app.dependency_overrides[get_tenant_id] = lambda: uuid4()
    for method, path in [('GET','preview'),('GET','download'),('POST','index'),('DELETE','')]:
        assert client.request(method,f'/api/v2/materials/{fid}' + (f'/{path}' if path else '')).status_code == 404
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    assert client.delete(f'/api/v2/materials/{fid}').status_code == 204
    assert client.get(f'/api/v2/materials/{fid}/preview').status_code == 404
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(text('SELECT count(*) FROM rag_chunk WHERE source_id=:id'), {'id':fid}) == 0
        purge = session.execute(text("SELECT args FROM procrastinate_jobs WHERE task_name='learn_core.jobs.tasks.purge_material' AND args->>'tenant'=:tid ORDER BY id DESC LIMIT 1"), {'tid':str(tenant[0])}).scalar_one()
    purge_material_task(**purge)
    assert not list(Path(get_settings().files_root).rglob(result['sha256']))


@db_test
def test_delete_during_embedding_never_restores_index_and_reupload_survives_old_cleanup(tenant, library, monkeypatch):
    client, _ = library
    result = client.post(f'/api/v2/projects/{tenant[1]}/materials', files={'file':('first.txt',b'hello learning')}).json()
    fake_embed(monkeypatch, lambda: client.delete(f"/api/v2/materials/{result['fileId']}"))
    index_material_task(tenant=str(tenant[0]), job_id=result['jobId'], file_id=result['fileId'])
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(text('SELECT count(*) FROM rag_chunk WHERE source_id=:id'), {'id':result['fileId']}) == 0
        assert session.scalar(select(JobProgress).where(JobProgress.job_id == result['jobId'])).state == 'cancelled'
    again = client.post(f'/api/v2/projects/{tenant[1]}/materials', files={'file':('again.txt',b'hello learning')}).json()
    key = f"{tenant[0]}/material/{result['sha256']}"
    purge_material_task(tenant=str(tenant[0]),storage_key=key)
    assert client.get(f"/api/v2/materials/{again['fileId']}/download").content == b'hello learning'


@db_test
def test_quota_queue_failure_and_invalid_extension_leave_no_files_or_jobs(tenant, library, monkeypatch):
    client, _ = library
    with session_scope() as session:
        session.get(Tenant, tenant[0]).quota_bytes = 3
    response = client.post(f'/api/v2/projects/{tenant[1]}/materials', files={'file':('a.txt',b'1234')})
    assert response.status_code == 507
    assert client.post(f'/api/v2/projects/{tenant[1]}/materials', files={'file':('a.exe',b'12')}).status_code == 422
    def fail(*args,**kwargs): raise RuntimeError('simulated queue failure')
    monkeypatch.setattr(materials, 'defer', fail)
    response = client.post(f'/api/v2/projects/{tenant[1]}/materials', files={'file':('a.txt',b'12')})
    assert response.status_code == 500
    with tenant_context(tenant[0]), session_scope() as session:
        assert not list(session.scalars(select(StoredFile)))
        assert not list(session.scalars(select(JobProgress)))
    assert not [f for f in Path(get_settings().files_root).rglob('*') if f.is_file()]
