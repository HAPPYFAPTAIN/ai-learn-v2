"""Only durable queued chat remains public; model billing IDs are global."""
import re
from uuid import uuid4
from learn_api.app import create_app
from learn_core.llm.event_id import next_event_id, step_event


def test_sync_chat_route_is_retired():
    assert '/api/v2/projects/{project_id}/chat' not in create_app().openapi()['paths']


def test_event_ids_survive_counter_rebuild_and_are_global_for_both_callers():
    # UUID allocation has no database dependency or resettable counter.
    tenants = [uuid4(), uuid4()]
    ids = {step_event(next_event_id(None, tenant_id=t, kind=k), 1)
           for t in tenants for k in ['j', 'r'] for _ in range(50)}
    assert len(ids) == 200
    assert all(re.fullmatch(r'ln-[jr]-[0-9a-f]{32}-1-1', v) and len(v) < 100 for v in ids)
