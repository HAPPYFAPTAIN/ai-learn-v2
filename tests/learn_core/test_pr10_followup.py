"""Durable creation replay and daily report contracts after PR #10."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from learn_api.app import create_app
from learn_api.deps import get_session, get_tenant_id
from learn_core.db.engine import session_scope
from learn_core.db.models import Card, CreationRequest, Knode, Note, ProgressRecord, Project, Tenant
from learn_core.learning import reports
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import db_test, tenant


@pytest.fixture
def api(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        node = Knode(project_id=tenant[1], code="1", title="chapter")
        session.add(node)
        session.flush()
        nid = node.id
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as client:
        yield client, nid


def creation(kind, tenant, nid):
    if kind == "note":
        return f"/api/v2/projects/{tenant[1]}/notes", {"nodeId": nid, "content": "note", "selection": "quote"}
    return "/api/v2/cards", {"projectId": tenant[1], "nodeId": nid, "front": "Q", "back": "A"}


@db_test
@pytest.mark.parametrize("kind", ["note", "card"])
def test_creation_replay_conflict_and_deliberate_duplicate(tenant, api, kind):
    client, nid = api
    url, payload = creation(kind, tenant, nid)
    payload["requestId"] = str(uuid4())
    first = client.post(url, json=payload)
    assert first.status_code == 201, first.text
    replay = client.post(url, json=payload)
    assert replay.status_code == 201 and replay.json() == first.json()
    changed = {**payload, ("content" if kind == "note" else "front"): "different"}
    assert client.post(url, json=changed).status_code == 409
    independent = client.post(url, json={**payload, "requestId": str(uuid4())})
    assert independent.status_code == 201 and independent.json()["id"] != first.json()["id"]


@db_test
@pytest.mark.parametrize("kind", ["note", "card"])
def test_two_concurrent_creates_share_one_record(tenant, api, kind):
    client, nid = api
    url, payload = creation(kind, tenant, nid)
    payload["requestId"] = str(uuid4())
    ready = Barrier(2)
    def send():
        ready.wait(timeout=10)
        result = client.post(url, json=payload)
        assert result.status_code == 201, result.text
        return result.json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: send(), range(2)))
    assert replies[0] == replies[1]
    with tenant_context(tenant[0]), session_scope() as session:
        model = Note if kind == "note" else Card
        assert session.scalar(select(func.count()).select_from(model)) == 1


@db_test
def test_creation_rollback_does_not_consume_request_id(tenant, api):
    client, nid = api
    url, payload = creation("note", tenant, nid)
    payload["requestId"] = str(uuid4())
    async def rollback():
        with tenant_context(tenant[0]), session_scope() as session:
            yield session
            session.rollback()
    client.app.dependency_overrides[get_session] = rollback
    assert client.post(url, json=payload).status_code == 201
    del client.app.dependency_overrides[get_session]
    saved = client.post(url, json=payload)
    assert saved.status_code == 201
    assert client.post(url, json=payload).json()["id"] == saved.json()["id"]
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Note)) == 1


@db_test
def test_deleted_creation_cannot_be_resurrected_by_replay(tenant, api):
    client, nid = api
    url, payload = creation("note", tenant, nid)
    payload["requestId"] = str(uuid4())
    result = client.post(url, json=payload)
    assert result.status_code == 201
    assert client.delete(f"/api/v2/notes/{result.json()['id']}").status_code == 204
    assert client.post(url, json=payload).status_code == 409
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Note)) == 0
        assert session.scalar(select(CreationRequest)).response == {}


@db_test
def test_creation_receipts_isolate_identical_uuids_between_accounts(tenant, api):
    client, nid = api
    request_id = str(uuid4())
    url, payload = creation("note", tenant, nid)
    first = client.post(url, json={**payload, "requestId": request_id})
    assert first.status_code == 201
    with session_scope() as session:
        other = Tenant(official_user_id=f"receipt-{uuid4().hex}")
        session.add(other)
        session.flush()
        other_id = other.id
    try:
        with tenant_context(other_id), session_scope() as session:
            assert session.scalar(select(func.count()).select_from(CreationRequest)) == 0
            project = Project(title="other", topic="other")
            session.add(project)
            session.flush()
            node = Knode(project_id=project.id, code="1", title="other")
            session.add(node)
            session.flush()
            other_pid, other_nid = project.id, node.id
        client.app.dependency_overrides[get_tenant_id] = lambda: other_id
        result = client.post(f"/api/v2/projects/{other_pid}/notes", json={
            "nodeId": other_nid, "content": "private", "requestId": request_id,
        })
        assert result.status_code == 201 and result.json()["id"] != first.json()["id"]
        with tenant_context(other_id), session_scope() as session:
            assert session.scalar(select(func.count()).select_from(CreationRequest)) == 1
    finally:
        client.app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
        with session_scope() as session:
            session.delete(session.get(Tenant, other_id))


@db_test
def test_project_deletion_erases_receipt_content_and_preserves_tombstones(tenant, api):
    client, nid = api
    for kind in ("note", "card"):
        url, payload = creation(kind, tenant, nid)
        assert client.post(url, json={**payload, "requestId": str(uuid4())}).status_code == 201
    assert client.delete(f"/api/v2/projects/{tenant[1]}").status_code == 204
    with tenant_context(tenant[0]), session_scope() as session:
        receipts = list(session.scalars(select(CreationRequest)))
        assert len(receipts) == 2
        assert all(receipt.response == {} for receipt in receipts)


@db_test
def test_report_api_filters_and_paginates_distinct_days(tenant, api):
    client, _ = api
    today = datetime.now(timezone.utc).date()
    with tenant_context(tenant[0]), session_scope() as session:
        for offset in range(5):
            for _ in range(2):
                reports.build_report(session, project_id=tenant[1], day=today-timedelta(days=offset))
    url = f"/api/v2/projects/{tenant[1]}/reports"
    result = client.get(url, params={"fromDate": str(today-timedelta(days=3)), "toDate": str(today-timedelta(days=1)), "limit": 2, "offset": 1})
    assert result.status_code == 200, result.text
    assert [row["date"] for row in result.json()["items"]] == [str(today-timedelta(days=2)), str(today-timedelta(days=3))]
    assert client.get(url, params={"fromDate": str(today), "toDate": str(today-timedelta(days=1))}).status_code == 422
    assert client.get(url, params={"limit": 0}).status_code == 422


@db_test
def test_report_limit_counts_days_and_selects_latest_snapshot(tenant):
    today = datetime.now(timezone.utc).date()
    with tenant_context(tenant[0]), session_scope() as session:
        for offset in range(1, 30):
            reports.build_report(session, project_id=tenant[1], day=today-timedelta(days=offset))
        for _ in range(31):
            latest = reports.build_report(session, project_id=tenant[1], day=today)
        rows = reports.list_reports(session, project_id=tenant[1])
        assert len(rows) == len({r.report_date for r in rows}) == 30
        assert rows[0].id == latest.id


@db_test
def test_reports_use_shanghai_day_and_half_open_boundaries(tenant, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 17, 17, 0, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(reports, "datetime", FrozenDateTime)
    with tenant_context(tenant[0]), session_scope() as session:
        for timestamp, minutes in (("2026-11-17T15:59:59+00:00", 100), ("2026-11-17T16:00:00+00:00", 5), ("2026-11-18T16:00:00+00:00", 100)):
            session.add(ProgressRecord(project_id=tenant[1], metric="minutes", value=minutes, recorded_at=datetime.fromisoformat(timestamp)))
        session.flush()
        row = reports.build_report(session, project_id=tenant[1])
        assert row.report_date.date().isoformat() == "2026-11-18"
        assert row.study_minutes == 5
