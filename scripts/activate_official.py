#!/usr/bin/env python3
"""Switch only the learning service, with a private snapshot and automatic rollback."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--release',required=False)
parser.add_argument('--host',required=True,help='Explicit SSH target')
parser.add_argument('--expected-hostname',required=True,help='Verified production hostname')
parser.add_argument('--rollback',help='Private backup directory returned by a previous activation')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
release=args.release or (None if args.rollback else None)
program=r'''
import datetime,fcntl,hashlib,json,os,pathlib,shutil,socket,subprocess,sys,tarfile,time,urllib.request
assert os.geteuid()==0 and socket.gethostname()==sys.argv[3]
lock=os.open('/run/lock/learn-release.lock',os.O_CREAT|os.O_WRONLY,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
unit=pathlib.Path('/etc/systemd/system/aethericai-learn.service')
nginx=pathlib.Path('/etc/nginx/snippets/aethericai-official-locations.conf')
private=pathlib.Path('/var/lib/learn-everything-platform');private.mkdir(mode=0o700,exist_ok=True)
def run(*argv):
 result=subprocess.run(argv,capture_output=True,text=True,timeout=60)
 if result.returncode:raise RuntimeError('Service validation failed: '+argv[0]+' '+result.stderr[-1200:])
 return result.stdout.strip()
def write_private(path,text):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as stream:stream.write(text)
def restore(backup):
 assert backup.parent in {pathlib.Path('/var/backups/learn-everything'),pathlib.Path('/data/learn-everything/backups')} and backup.stat().st_uid==0 and not backup.stat().st_mode&0o077
 run('systemctl','stop','aethericai-learn.service')
 shutil.copy2(backup/'aethericai-learn.service',unit)
 for name in ['service.env','deployment.json']:
  if (backup/name).exists():shutil.copy2(backup/name,private/name)
 if (backup/'deployment.json').exists():
  previous=pathlib.Path(json.loads((backup/'deployment.json').read_text())['release'])
  current=previous.parent.parent/'current';next_link=current.with_name('.rollback.next')
  next_link.symlink_to(previous,target_is_directory=True);os.replace(next_link,current)
 # Only our dedicated stylesheet exception was added to this shared snippet.
 before=(backup/'official-locations.conf').read_bytes()
 current=nginx.read_bytes();addition=(backup/'framework-css.conf').read_bytes()
 if current==before+addition:nginx.write_bytes(before)
 elif current!=before:raise RuntimeError('Nginx changed independently; refusing to overwrite it')
 run('nginx','-t');run('systemctl','daemon-reload');run('systemctl','start','aethericai-learn.service');run('systemctl','reload','nginx')
 assert run('systemctl','is-active','aethericai-learn.service')=='active'
if sys.argv[1]=='rollback':
 backup=pathlib.Path(sys.argv[2]);restore(backup)
 print(json.dumps({'rolledBack':True,'backup':str(backup),'newAccountDataRetained':True}));raise SystemExit(0)
release=pathlib.Path(sys.argv[2]);assert release.parent==pathlib.Path('/data/learn-everything/releases') and release.resolve()==release
r=json.loads((release/'RELEASE.json').read_text());assert r.get('commit') and r['id']==release.name
assert json.loads((release/'BUILD.json').read_text())['passed']
for name,digest in r['inputs'].items():
 assert hashlib.sha256((release/name).read_bytes()).hexdigest()==digest,'Published source drift'
for artifact in json.loads((release/'BUILD.json').read_text())['gradioComponentArtifacts']:
 assert hashlib.sha256((release/artifact['path']).read_bytes()).hexdigest()==artifact['sha256'],'Generated declaration drift'
assert run('systemctl','is-active','aethericai-learn.service')=='active'
old_unit=unit.read_text();native='le_platform.broker:app' in old_unit
if native:
 previous=json.loads((private/'deployment.json').read_text());old_release=pathlib.Path(previous['release'])
 assert str(old_release) in old_unit and old_release.parent==release.parent,'Unexpected native deployment'
 users=pathlib.Path('/data/learn-everything/accounts/users')
 for env_path in pathlib.Path('/data/learn-everything/accounts/private').glob('le_*.env'):
  env={k:json.loads(v) for line in env_path.read_text().splitlines() for k,_,v in [line.partition('=')]}
  try:
   req=urllib.request.Request('http://127.0.0.1:'+env['LE_SERVER_PORT']+'/platform/activity',headers={'X-Learn-User':env['LE_OFFICIAL_USER'],'X-Learn-Worker-Key':env['LE_WORKER_KEY']})
   with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=3) as reply:assert json.load(reply)['busy'] is False,'Active learning generation must drain before upgrade'
  except (ConnectionError,urllib.error.URLError):
   name='aethericai-learn-'+env_path.stem+'-'
   running=run('systemctl','list-units','--state=running','--no-legend','--plain',name+'*.service')
   assert not running,'Cannot read active account status; refusing upgrade'
 size=sum(path.stat().st_size for path in users.rglob('*') if path.is_file() and not path.is_symlink() and 'work' not in path.relative_to(users).parts)
 assert shutil.disk_usage('/data').free>size+1024**3,'Insufficient cloud space for a private native snapshot'
else:assert '/srv/learn-everything/releases/20261009-learning-ui' in old_unit,'Unexpected existing learning deployment'
old_nginx=nginx.read_bytes();assert b'/official/learn-everything/' in old_nginx
if not native:assert b'location = /assets/index-BOW2xVAS.css' not in old_nginx,'Unexpected stylesheet route already installed'
pid=run('systemctl','show','aethericai-learn.service','--property=MainPID','--value')
prior=dict(item.split(b'=',1) for item in pathlib.Path('/proc/'+pid+'/environ').read_bytes().split(b'\0') if b'=' in item)
environment={name:prior[name.encode()].decode() for name in ['OPENAI_API_KEY','OPENAI_API_BASE','OPENAI_CHAT_MODEL']}
environment.update(LE_PLATFORM_RELEASE=str(release),LE_PLATFORM_PYTHON='/data/learn-everything/runtime/python311/bin/python',
 LE_BROKER_UNIT='aethericai-learn.service',LE_PLATFORM_STATE='/data/learn-everything/accounts',LE_MAX_WORKERS='2',
 LE_EMBEDDING_PATH='/data/learn-everything/runtime/models/multilingual-minilm',PYTHONUNBUFFERED='1',
 PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(release/'platform'))
new_env=''
for name,value in environment.items():
 assert '\n' not in value and '\r' not in value and '\x00' not in value
 new_env+=name+'='+json.dumps(value,ensure_ascii=False)+'\n'
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
backup=(pathlib.Path('/data/learn-everything/backups') if native else pathlib.Path('/var/backups/learn-everything'))/stamp;backup.mkdir(mode=0o700,parents=True)
shutil.copy2(unit,backup/'aethericai-learn.service');(backup/'official-locations.conf').write_bytes(old_nginx)
for name in ['service.env','deployment.json']:
 if (private/name).exists():shutil.copy2(private/name,backup/name)
addition=b'' if b'location = /assets/index-BOW2xVAS.css' in old_nginx else b'\n'+(release/'product/deploy/framework-css.conf').read_bytes()+b'\n'
(backup/'framework-css.conf').write_bytes(addition)
new_unit=(release/'product/deploy/aethericai-learn.service').read_text().replace('@RELEASE@',str(release))
prepared=backup/'prepared';prepared.mkdir(mode=0o700)
(prepared/'aethericai-learn.service').write_text(new_unit)
write_private(private/'service.env.new',new_env)
run('systemd-analyze','verify',str(prepared/'aethericai-learn.service'))
assert unit.read_text()==old_unit and nginx.read_bytes()==old_nginx,'Deployment changed during preparation'
nginx.write_bytes(old_nginx+addition)
try:run('nginx','-t')
except BaseException:
 nginx.write_bytes(old_nginx);raise
try:
 for line in run('systemctl','list-units','--all','--plain','--no-legend','learn-candidate-*.service').splitlines():
  run('systemctl','stop',line.split()[0])
 run('systemctl','stop','aethericai-learn.service')
 # Old service is stopped: the complete old data/config/cache snapshot is consistent.
 with tarfile.open(backup/'old-state.tar.gz','w:gz') as pack:
  pack.add('/data/learn-everything/accounts/users' if native else '/var/lib/aethericai-learn',arcname='users' if native else 'aethericai-learn',recursive=True)
 assert (backup/'old-state.tar.gz').stat().st_size>0
 unit.write_text(new_unit);os.replace(private/'service.env.new',private/'service.env')
 run('systemctl','daemon-reload');run('systemctl','start','aethericai-learn.service')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for attempt in range(60):
  try:
   with opener.open('http://127.0.0.1:7860/healthz',timeout=1) as reply:
    assert json.load(reply)['release']==release.name
   break
  except OSError:time.sleep(.5)
 else:raise RuntimeError('New learning broker did not become ready')
 run('nginx','-t');run('systemctl','reload','nginx')
 current=release.parent.parent/'current'
 assert not current.exists() or current.is_symlink()
 next_link=current.with_name('.current.next');next_link.symlink_to(release,target_is_directory=True);os.replace(next_link,current)
 report={'activated':True,'release':str(release),'commit':r['commit'],'backup':str(backup),
  'service':'aethericai-learn.service','accountState':'/data/learn-everything/accounts','otherServicesRestarted':False}
 write_private(private/'deployment.json',json.dumps(report,indent=2))
 print(json.dumps(report))
except BaseException:
 restore(backup);raise
'''
if not args.release and not args.rollback:parser.error('--release or --rollback is required')
(root/'output/official').mkdir(parents=True,exist_ok=True)
mode='rollback' if args.rollback else 'activate'
run=subprocess.run(['ssh','-o','BatchMode=yes',args.host,'python3 -c '+shlex.quote(program)+' '+shlex.quote(mode)+' '+shlex.quote(args.rollback or release)+' '+shlex.quote(args.expected_hostname)],capture_output=True,text=True)
print(run.stdout)
if run.returncode:print(run.stderr[-2200:])
elif not args.rollback:(root/'output/official/deployment.json').write_text(run.stdout)
raise SystemExit(run.returncode)
