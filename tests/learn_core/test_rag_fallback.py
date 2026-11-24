"""The no-vector branch never emits vector SQL, even without a database."""

from learn_core.rag.store import hybrid_search


class EmptyResult:
    def mappings(self):
        return []


class RecordingSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        return EmptyResult()


def test_text_only_fallback_emits_no_vector_query_or_ann_settings():
    session = RecordingSession()
    assert hybrid_search(
        session, index_id="material", query="全文检索", query_vector=None,
    ) == []
    assert len(session.calls) == 1
    sql, parameters = session.calls[0]
    assert "rag_chunk" in sql
    assert "rag_embedding" not in sql and "<=>" not in sql
    assert "qvec" not in parameters
