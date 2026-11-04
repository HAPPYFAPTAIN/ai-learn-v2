"""Pack and verify a committed standalone checkout in the existing learning release layout."""
import argparse
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS={'__pycache__','node_modules','.venv','dist','build','.git','.pytest_cache'}
FORBIDDEN_SUFFIXES={'.pyc','.pyo','.exe','.dll','.so','.dylib','.whl','.zip','.tar','.gz',
    '.gguf','.onnx','.pt','.bin','.db','.sqlite','.sqlite3','.map'}


def git(*args,cwd=ROOT):
    return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()


def runtime_files(root,policy):
    tracked=set(git('ls-files','-z',cwd=root).split('\0'))-{''}
    for name in [*policy['files'],*policy['exclude'],*policy['trees']]:
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:raise ValueError('Invalid release policy path')
    missing=set(policy['files'])-tracked
    if missing:raise ValueError('Required runtime inputs are not tracked: '+','.join(sorted(missing)))
    for tree in policy['trees']:
        if not any(name.startswith(tree+'/') for name in tracked):raise ValueError('Missing runtime tree: '+tree)
    for name in sorted(tracked):
        if name in policy['exclude']:continue
        if name not in policy['files'] and not any(name.startswith(tree+'/') for tree in policy['trees']):continue
        path=root/name
        if path.is_symlink() or not path.is_file():raise ValueError('Release inputs must be regular files: '+name)
        if FORBIDDEN_PARTS.intersection(path.relative_to(root).parts) or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise ValueError('Generated or binary runtime input: '+name)
        if path.name=='.env' or path.name.startswith('.env.'):raise ValueError('Private runtime configuration: '+name)
        yield name,path


def inputs(root=ROOT):
    policy=json.loads((root/'runtime/release-policy.json').read_text())
    selected={}
    for name,path in runtime_files(root,policy['project']):
        if name.startswith('le_platform/'):target='platform/'+name
        elif name.startswith(('runtime/','deploy/')) or name=='INTEGRATION.json':target='product/'+name
        else:target=('input-stubs/' if path.suffix=='.pyi' else 'source/')+name
        selected[target]=path
    for name,path in runtime_files(root/'kotaemon',policy['kotaemon']):
        target=('input-stubs/' if path.suffix=='.pyi' else 'source/')+'kotaemon/'+name
        selected[target]=path
    return selected


def pack(output):
    if git('status','--porcelain','--untracked-files=normal'):
        raise ValueError('Commit authored inputs before packaging; ignore only runtime output')
    expected=git('rev-parse','HEAD:kotaemon')
    if git('rev-parse','HEAD',cwd=ROOT/'kotaemon')!=expected or git('status','--porcelain',cwd=ROOT/'kotaemon'):
        raise ValueError('Kotaemon must match the clean pinned submodule')
    commit=git('rev-parse','HEAD');files=inputs()
    digests={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sorted(files.items())}
    metadata={'schemaVersion':1,'id':datetime.now(timezone.utc).strftime('%Y%m%d')+'-learn-'+commit[:12],
        'commit':commit,'repository':'https://github.com/AetherMindHarness/ai-learn',
        'upstream':json.loads((ROOT/'INTEGRATION.json').read_text())['upstream']['commit'],
        'kotaemonCommit':expected,'sourceDigest':hashlib.sha256(json.dumps(digests,sort_keys=True).encode()).hexdigest(),
        'inputs':digests,'framework':'gradio==4.44.1','accountMode':'isolated-unix-worker'}
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    archive=output/(metadata['id']+'.tar.gz')
    with archive.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz') as tar:
        for name,path in sorted(files.items()):tar.add(path,arcname=name,recursive=False)
        data=(json.dumps(metadata,indent=2)+'\n').encode();info=tarfile.TarInfo('RELEASE.json');info.size=len(data);info.mode=0o644
        tar.addfile(info,io.BytesIO(data))
    report={'archive':str(archive),'id':metadata['id'],'commit':commit,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'inputs':len(files)}
    (output/'latest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


def verify(release):
    release=release.resolve();metadata=json.loads((release/'RELEASE.json').read_text())
    for name,digest in metadata['inputs'].items():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:raise ValueError('Invalid release input')
        candidate=release/name
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(release):raise ValueError('Linked release input')
        if hashlib.sha256(candidate.read_bytes()).hexdigest()!=digest:raise ValueError('Source input mismatch: '+name)
    if hashlib.sha256(json.dumps(metadata['inputs'],sort_keys=True).encode()).hexdigest()!=metadata['sourceDigest']:
        raise ValueError('Source manifest digest mismatch')
    return metadata


def install(archive):
    if os.geteuid()!=0:raise ValueError('Install requires root for immutable release ownership')
    parent=Path('/data/learn-everything/releases')
    if not Path('/data').is_mount():raise ValueError('The product data volume must be mounted')
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers();names=set();total=0
        for member in members:
            path=PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or '..' in path.parts or member.name in names:
                raise ValueError('Unsafe archive member')
            names.add(member.name);total+=member.size
        if total>512*1024**2:raise ValueError('Source archive exceeds 512 MiB')
        metadata=json.load(tar.extractfile('RELEASE.json'))
        if names!=set(metadata['inputs'])|{'RELEASE.json'}:raise ValueError('Unlisted archive inputs')
        import re
        if not re.fullmatch(r'\d{8}-learn-[a-f0-9]{12}',metadata['id']):raise ValueError('Invalid release ID')
        target=parent/metadata['id'];preparing=parent/('.'+metadata['id']+'.preparing')
        if target.exists() or preparing.exists():raise ValueError('Release already exists')
        preparing.mkdir(mode=0o755,parents=True)
        tar.extractall(preparing,filter='data')
    verify(preparing)
    for current,dirs,files in os.walk(preparing):
        os.chmod(current,0o755)
        for name in files:os.chmod(Path(current)/name,0o644)
    subprocess.run(['/usr/bin/python3',str(preparing/'platform/le_platform/build.py'),str(preparing)],check=True)
    verify(preparing);preparing.rename(target)
    print(json.dumps({'release':str(target),'commit':metadata['commit'],'liveChanged':False}))


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='action',required=True)
    p=commands.add_parser('pack');p.add_argument('--output',type=Path,default=ROOT/'output/official')
    p=commands.add_parser('verify');p.add_argument('release',type=Path)
    p=commands.add_parser('install');p.add_argument('archive',type=Path)
    args=parser.parse_args()
    if args.action=='pack':pack(args.output)
    elif args.action=='verify':print(json.dumps({'verified':True,'commit':verify(args.release)['commit']}))
    else:install(args.archive)


if __name__=='__main__':main()
