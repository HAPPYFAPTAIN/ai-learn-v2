import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PATH=Path(__file__).resolve().parents[1]/'scripts/official_release.py'
spec=importlib.util.spec_from_file_location('official_release',PATH)
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


def test_release_layout_preserves_source_platform_and_submodule():
    files=release.inputs()
    assert files['source/custom_app.py'].is_file()
    assert files['platform/le_platform/broker.py'].is_file()
    assert files['source/kotaemon/flowsettings.py'].is_file()
    assert files['product/runtime/requirements-linux-py311.lock'].is_file()
    assert all(not name.endswith('.pyi') or name.startswith('input-stubs/') for name in files)
    assert not any('.git/' in name or '.env'==Path(name).name for name in files)


def test_verify_rejects_modified_source_and_path_escape(tmp_path):
    file=tmp_path/'source';file.mkdir();(file/'app.py').write_text('original')
    inputs={'source/app.py':hashlib.sha256(b'original').hexdigest()}
    metadata={'commit':'fixture','inputs':inputs,'sourceDigest':hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()}
    (tmp_path/'RELEASE.json').write_text(json.dumps(metadata))
    assert release.verify(tmp_path)['commit']=='fixture'
    (file/'app.py').write_text('modified')
    with pytest.raises(ValueError,match='mismatch'):release.verify(tmp_path)
    metadata['inputs']={'../outside':'anything'};(tmp_path/'RELEASE.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError,match='Invalid'):release.verify(tmp_path)
