import concurrent.futures
import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest

PATH = Path(__file__).resolve().parents[1] / 'learning_ext/citation_visualization.py'


@pytest.fixture
def adapter(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('citation_adapter_test', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_IMPLEMENTATION', '_citation_fixture_implementation')
    monkeypatch.delitem(sys.modules, module._IMPLEMENTATION, raising=False)
    def source(text):
        path = tmp_path / 'fixture.py'
        path.write_text(text)
        monkeypatch.setattr(module, '_SOURCE', path)
        monkeypatch.setattr(module, '_SOURCE_SHA256', hashlib.sha256(path.read_bytes()).hexdigest())
    yield module, source
    sys.modules.pop(module._IMPLEMENTATION, None)


def test_concurrent_first_calls_execute_implementation_once(adapter, tmp_path):
    module, source = adapter
    count = tmp_path / 'loads.txt'
    source(f"from pathlib import Path\nimport time\nwith Path({str(count)!r}).open('a') as out:out.write('load\\n')\ntime.sleep(.03)\nclass CreateCitationVizPipeline:pass\n")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        classes = list(pool.map(lambda _: module.implementation(), range(16)))
    assert len({id(cls) for cls in classes}) == 1
    assert count.read_text() == 'load\n'


def test_failure_is_not_cached_and_next_call_can_retry(adapter, tmp_path):
    module, source = adapter
    marker = tmp_path / 'fail-once'
    source(f"from pathlib import Path\np=Path({str(marker)!r})\nif not p.exists():\n p.touch()\n raise ImportError('injected optional dependency failure')\nclass CreateCitationVizPipeline:pass\n")
    with pytest.raises(ImportError):
        module.implementation()
    assert module._implementation is None
    assert module._IMPLEMENTATION not in sys.modules
    assert module.implementation().__name__ == 'CreateCitationVizPipeline'


def test_source_drift_refuses_execution(adapter, tmp_path):
    module, source = adapter
    marker = tmp_path / 'executed'
    source(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nclass CreateCitationVizPipeline:pass\n")
    module._SOURCE.write_text(module._SOURCE.read_text() + '\n# changed\n')
    with pytest.raises(RuntimeError, match='source changed'):
        module.implementation()
    assert not marker.exists()


def test_checked_in_upstream_matches_reviewed_implementation():
    module = importlib.util.module_from_spec(importlib.util.spec_from_file_location('citation_hash_test', PATH))
    module.__spec__.loader.exec_module(module)
    assert hashlib.sha256(module._SOURCE.read_bytes()).hexdigest() == module._SOURCE_SHA256
