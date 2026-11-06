"""Defer the pinned optional citation plot implementation until a plot is requested."""
import hashlib
import importlib
import importlib.util
from pathlib import Path
import sys
import threading
from types import ModuleType
from typing import Any

_SOURCE = Path(__file__).resolve().parents[1] / 'kotaemon/libs/ktem/ktem/utils/visualize_cited.py'
_SOURCE_SHA256 = '1b575d8cd42daece321dd8e07bde490b3dd19060f4c6875c1cf97a0c39221265'
_MODULE = 'ktem.utils.visualize_cited'
_IMPLEMENTATION = '_learn_upstream_citation_visualization'
_lock = threading.Lock()
_implementation = None


def implementation():
    global _implementation
    # Only the implementation class is shared. Embeddings, queries and projectors
    # belong to each invocation. Failed imports leave no cached success; retry is allowed.
    with _lock:
        if _implementation is not None:
            return _implementation
        if hashlib.sha256(_SOURCE.read_bytes()).hexdigest() != _SOURCE_SHA256:
            raise RuntimeError('Citation visualization source changed; review the adapter before upgrading.')
        spec = importlib.util.spec_from_file_location(_IMPLEMENTATION, _SOURCE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[_IMPLEMENTATION] = module
        try:
            spec.loader.exec_module(module)
            _implementation = module.CreateCitationVizPipeline
        except BaseException:
            if sys.modules.get(_IMPLEMENTATION) is module:
                sys.modules.pop(_IMPLEMENTATION, None)
            raise
        return _implementation


def configure_citation_visualization():
    """Install once on the startup thread, before importing the application."""
    if _MODULE in sys.modules:
        return
    from kotaemon.base import BaseComponent, Document
    from kotaemon.embeddings.base import BaseEmbeddings
    parent = importlib.import_module('ktem.utils')

    class DeferredCitationVizPipeline(BaseComponent):
        embedding: BaseEmbeddings
        projector: Any = None

        def run(self, context, question):
            queue = getattr(self, '_queue', None)
            if _implementation is None and queue is not None:
                self.report_output(Document(channel='info', content='正在准备引用分布图，首次使用可能需要稍候。'))
            try:
                original = implementation()(embedding=self.embedding)
                result = self._prepare_child(original, 'citation_plot')(context, question)
                self.projector = original.projector
                return result
            except Exception:
                if queue is not None:
                    self.report_output(Document(channel='info', content='引用分布图暂时无法生成，文字回答和资料引用仍可使用。'))
                raise

    module = ModuleType(_MODULE)
    module.__file__ = str(_SOURCE)
    module.__package__ = 'ktem.utils'
    module.__spec__ = importlib.util.spec_from_loader(_MODULE, loader=None, origin=str(_SOURCE))
    DeferredCitationVizPipeline.__module__ = _MODULE
    DeferredCitationVizPipeline.__name__ = 'CreateCitationVizPipeline'
    DeferredCitationVizPipeline.__qualname__ = 'CreateCitationVizPipeline'
    module.CreateCitationVizPipeline = DeferredCitationVizPipeline
    sys.modules[_MODULE] = module
    parent.visualize_cited = module
