"""Read-only check of the pinned Python environment, embeddings and NLTK assets."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import subprocess
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime',type=Path,default=Path('/data/learn-everything/runtime'))
args=parser.parse_args();specs=Path(__file__).resolve().parents[1]/'runtime';issues=[];packages=0
if sys.version_info[:2]!=(3,11):issues.append('Python 3.11 is required')
for line in (specs/'requirements-linux-py311.lock').read_text().splitlines():
    if not line or line.startswith('#'):continue
    name,version=line.split('==',1);packages+=1
    try:actual=metadata.version(name)
    except metadata.PackageNotFoundError:actual=None
    if actual!=version:issues.append('Package version mismatch: '+name)
for name,digest in json.loads((specs/'model.json').read_text())['files'].items():
    path=args.runtime/'models/multilingual-minilm'/name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:issues.append('Model file mismatch: '+name)
for name,item in json.loads((specs/'nltk.json').read_text()).items():
    path=args.runtime/'nltk'/item['path']
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:issues.append('NLTK archive mismatch: '+name)
    if not path.parent.joinpath(name).is_dir():issues.append('NLTK data missing: '+name)
check=subprocess.run([sys.executable,'-m','pip','check'],capture_output=True,text=True)
if check.returncode:issues.append('pip check failed')
print(json.dumps({'passed':not issues,'packages':packages,'issues':issues}))
raise SystemExit(bool(issues))
