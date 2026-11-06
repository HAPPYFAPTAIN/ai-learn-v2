"""Run with the pinned full Linux runtime, an isolated data directory and no model API."""
import os
import queue
import sys

import pytest

pytestmark = pytest.mark.skipif(os.getenv('LE_TEST_FULL_RUNTIME') != '1', reason='Pinned isolated learning runtime required')


def test_full_app_import_defers_umap_and_real_plot_matches_upstream(monkeypatch):
    import functools
    import hashlib
    from learning_ext import citation_visualization as adapter
    adapter.configure_citation_visualization()
    from learning_ext.app import LearningApp
    app = LearningApp()
    app.make()
    assert 'umap' not in sys.modules
    from ktem.utils.visualize_cited import CreateCitationVizPipeline
    import ktem.utils.visualize_cited as exported
    assert exported.CreateCitationVizPipeline is CreateCitationVizPipeline
    from kotaemon.embeddings.base import BaseEmbeddings
    from kotaemon.base import DocumentWithEmbedding
    import numpy as np

    class Embeddings(BaseEmbeddings):
        def invoke(self, text, **kwargs):
            values = [text] if isinstance(text, str) else text
            return [DocumentWithEmbedding(content=value, embedding=np.random.RandomState(
                int(hashlib.sha256(value.encode()).hexdigest()[:8], 16)).normal(size=8).tolist()) for value in values]

    from theflow.utils.modules import import_dotted_string
    assert import_dotted_string('ktem.utils.visualize_cited.CreateCitationVizPipeline', safe=False) is CreateCitationVizPipeline
    original_class = adapter.implementation()
    import umap
    monkeypatch.setattr(umap, 'UMAP', functools.partial(umap.UMAP, random_state=42, n_jobs=1, n_neighbors=3, n_epochs=10))
    contexts = ['reference '+str(i) for i in range(6)]
    wrapper = CreateCitationVizPipeline(embedding=Embeddings())
    wrapped_plot = wrapper(contexts, 'question')
    original_plot = original_class(embedding=Embeddings())(contexts, 'question')
    assert len(wrapped_plot.data) == len(original_plot.data) == 2
    for wrapped, original in zip(wrapped_plot.data, original_plot.data):
        assert wrapped.name == original.name
        np.testing.assert_allclose(wrapped.x, original.x)
        np.testing.assert_allclose(wrapped.y, original.y)
        assert list(wrapped.text) == list(original.text)
    assert wrapper.projector is not None
    assert CreateCitationVizPipeline(embedding=Embeddings()).projector is None

    # Failure stays local to the optional plot and reports a recoverable message.
    messages = queue.Queue()
    wrapper.set_output_queue(messages)
    def failed():
        raise ImportError('injected failure')
    monkeypatch.setattr(adapter, '_implementation', None)
    monkeypatch.setattr(adapter, 'implementation', failed)
    with pytest.raises(ImportError):
        wrapper(contexts, 'question')
    outputs = [messages.get_nowait().content for _ in range(messages.qsize())]
    assert any('正在准备' in str(item) for item in outputs)
    assert any('暂时无法' in str(item) for item in outputs)
