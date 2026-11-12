"""接口契约快照。

前端按这份清单对接，路由改名必须同步改这里——
比在文档里维护一张表可靠，因为改了就会红。
"""

from __future__ import annotations

from learn_api.app import create_app

EXPECTED = {
    ("GET", "/api/v2/projects"),
    ("POST", "/api/v2/projects"),
    ("GET", "/api/v2/projects/{project_id}"),
    ("PATCH", "/api/v2/projects/{project_id}"),
    ("DELETE", "/api/v2/projects/{project_id}"),
    ("GET", "/api/v2/projects/{project_id}/nodes"),
    ("POST", "/api/v2/projects/{project_id}/nodes"),
    ("PATCH", "/api/v2/nodes/{node_id}"),
    ("DELETE", "/api/v2/nodes/{node_id}"),
    ("POST", "/api/v2/projects/{project_id}/progress"),
    ("GET", "/api/v2/projects/{project_id}/progress"),
    ("GET", "/api/v2/projects/{project_id}/summary"),
    ("POST", "/api/v2/cards"),
    ("GET", "/api/v2/projects/{project_id}/cards"),
    ("GET", "/api/v2/review/due"),
    ("POST", "/api/v2/review/{card_id}"),
    ("POST", "/api/v2/projects/{project_id}/notes"),
    ("GET", "/api/v2/projects/{project_id}/notes"),
    ("PATCH", "/api/v2/notes/{note_id}"),
    ("DELETE", "/api/v2/notes/{note_id}"),
    ("POST", "/api/v2/projects/{project_id}/tasks"),
    ("GET", "/api/v2/projects/{project_id}/tasks"),
    ("PATCH", "/api/v2/tasks/{task_id}"),
    ("POST", "/api/v2/projects/{project_id}/quizzes"),
    ("GET", "/api/v2/projects/{project_id}/quizzes"),
    ("GET", "/api/v2/quizzes/{quiz_id}"),
    ("POST", "/api/v2/quizzes/{quiz_id}/submit"),
    ("POST", "/api/v2/projects/{project_id}/reports"),
    ("GET", "/api/v2/projects/{project_id}/reports"),
    ("POST", "/api/v2/projects/{project_id}/path"),
    ("POST", "/api/v2/projects/{project_id}/materials"),
    ("GET", "/api/v2/projects/{project_id}/materials"),
    ("POST", "/api/v2/projects/{project_id}/sources"),
    ("POST", "/api/v2/projects/{project_id}/chat"),
    ("POST", "/api/v2/search"),
    ("GET", "/api/v2/jobs/{job_id}"),
    ("GET", "/api/v2/jobs/{job_id}/events"),
    ("GET", "/healthz"),
}


def test_route_contract():
    spec = create_app().openapi()
    actual = {
        (method.upper(), path)
        for path, ops in spec["paths"].items()
        for method in ops
    }
    assert EXPECTED <= actual, f"缺少路由: {EXPECTED - actual}"
    extra = {a for a in actual - EXPECTED if a[1].startswith("/api/v2")}
    assert not extra, f"未登记的新路由（先想清楚再放行）: {extra}"
