import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

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
    for name in ['source/kotaemon/LICENSE.txt','source/kotaemon/docs/about.md','source/kotaemon/docs/usage.md',
                 'source/kotaemon/libs/ktem/ktem/assets/js/pdf_viewer.js',
                 'source/learning_ext/assets/vendor/pdfjs/pdf.worker.min.mjs','source/third_party/zcode/LICENSE']:
        assert name in files
    assert not any(name.startswith(('source/tests/','source/third_party/zcode/upstream/',
        'source/kotaemon/docs/images/','source/kotaemon/libs/kotaemon/tests/','source/kotaemon/libs/ktem/ktem_tests/')) for name in files)


def test_policy_keeps_runtime_assets_but_omits_development_files(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    paths=['app/main.py','app/assets/pdf.worker.min.mjs','app/assets/LICENSE','docs/demo.gif','tests/fixture.gguf','out.zip']
    for name in paths:
        file=tmp_path/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('fixture')
    subprocess.run(['git','add','.'],cwd=tmp_path,check=True)
    policy={'trees':['app'],'files':[],'exclude':[]}
    assert {name for name,_ in release.runtime_files(tmp_path,policy)}==set(paths[:3])


@pytest.mark.parametrize('name',['app/cache.pyc','app/data.sqlite3','app/.env','app/node_modules/index.js','app/native.dll'])
def test_generated_files_in_runtime_package_fail_publication(tmp_path,name):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    file=tmp_path/name;file.parent.mkdir(parents=True);file.write_text('fixture')
    subprocess.run(['git','add','.'],cwd=tmp_path,check=True)
    with pytest.raises(ValueError):list(release.runtime_files(tmp_path,{'trees':['app'],'files':[],'exclude':[]}))


def test_missing_required_input_fails_instead_of_building_incomplete_release(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    with pytest.raises(ValueError,match='not tracked'):
        list(release.runtime_files(tmp_path,{'trees':[],'files':['required.py'],'exclude':[]}))


def test_repository_guard_preserves_assets_and_rejects_generated_outputs(monkeypatch):
    monkeypatch.syspath_prepend(str(PATH.parent))
    from check_repository import violations
    good=['learning_ext/assets/vendor/pdfjs/pdf.worker.min.mjs','learning_ext/assets/logo.png',
          'learning_ext/assets/font.woff2','runtime/requirements-linux-py311.lock','deploy/service.env.example']
    bad=['output/old-report.md','tests/__pycache__/test_a.pyc','learning_ext/private.sqlite3',
         'dist/bundle.js','extra.egg-info/PKG-INFO','.env.production','vendor/tool.exe']
    assert violations(good+bad)==bad


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
