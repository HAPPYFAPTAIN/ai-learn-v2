"""Build Gradio declarations before publishing read-only account runtime code."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    release=Path(sys.argv[1])
    assert os.geteuid()==0 and release.parent==Path('/data/learn-everything/releases')
    runtime=Path('/data/learn-everything/runtime')
    work=Path('/data/learn-everything/build-work')/release.name
    work.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(release/'source/kotaemon/flowsettings.py',work/'flowsettings.py')
    env={**os.environ,'PYTHONPATH':':'.join(map(str,[work,release/'platform',release/'source',
        release/'source/kotaemon',release/'source/kotaemon/libs/ktem',release/'source/kotaemon/libs/kotaemon'])),
        'PYTHONDONTWRITEBYTECODE':'1','NLTK_DATA':str(runtime/'nltk'),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
        'KH_ENABLE_FIRST_SETUP':'False','KH_FEATURE_USER_MANAGEMENT':'False'}
    for key in ['OPENAI_API_KEY','COHERE_API_KEY','VOYAGE_API_KEY','MISTRAL_API_KEY','GOOGLE_API_KEY']:
        env[key]='unused-build-placeholder'
    with (work/'build.log').open('w') as log:
        result=subprocess.run([str(runtime/'python311/bin/python'),'-c',
            'import ktem.index.file.ui; import learning_ext.lesson_component'],cwd=work,env=env,
            stdout=log,stderr=log,timeout=180)
    if result.returncode:
        print((work/'build.log').read_text()[-2500:]);raise SystemExit(result.returncode)
    artifacts=[{'path':str(p.relative_to(release)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted((release/'source').rglob('*.pyi'))]
    receipt=json.loads((release/'RELEASE.json').read_text())
    for path,digest in receipt['inputs'].items():
        assert hashlib.sha256((release/path).read_bytes()).hexdigest()==digest,'Build altered an authored input'
    report={'passed':True,'gradio':'4.44.1','gradioComponentArtifacts':artifacts}
    (release/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'release':str(release),'artifacts':len(artifacts)}))


if __name__=='__main__':main()
