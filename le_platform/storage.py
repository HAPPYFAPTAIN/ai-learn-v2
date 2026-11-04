"""Per-account cloud-volume accounting, porting the DSH descriptor scanner.

The account's data/workspace/tmp/cache/home are billable. Immutable application,
shared models and platform download staging are not customer data. Never follow
links, cross devices, or count one inode twice. Quota is the same logical 5 GiB
contract as DSH; this is not a filesystem hard-quota installation.
"""
from contextlib import contextmanager
import errno
import hashlib
import os
from pathlib import Path,PurePosixPath
import stat
import time

INITIAL_STORAGE_BYTES=5*1024**3
PARTS=frozenset({'data','workspace','tmp','cache','home'})
CATEGORIES=(('records','学习与会话记录'),('sources','资料与检索索引'),
    ('previews','附件与预览'),('files','个人文件与导出'),('cache','运行缓存'),('other','其他文件'))
FLAGS=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW


class StorageQuotaExceeded(RuntimeError):
    status_code=507

    def __init__(self):super().__init__('5 GB个人学习空间已满，请在空间管理中下载或删除文件后继续。')


def account_root(owner,state):
    return Path(state)/'users'/('le_'+hashlib.sha256(owner.encode()).hexdigest()[:20])


def category(relative):
    parts=PurePosixPath(relative).parts
    if parts[0] in {'cache','home'}:return 'cache'
    if parts[0]=='tmp' or parts[:2]==('data','document_previews'):return 'previews'
    if parts[0]=='workspace' or len(parts)>1 and parts[1] in {'zip_cache_dir','markdown_cache_dir','chunks_cache_dir'}:return 'files'
    if parts[:2]==('data','user_data') and len(parts)>2:
        return 'records' if parts[2] in {'sql.db','sql.db-wal','sql.db-shm'} else 'sources'
    if Path(relative).suffix in {'.db','.sqlite3','.json','.jsonl','.log'}:return 'records'
    return 'other'


def snapshot(root):
    root=Path(root);sizes={key:0 for key,_ in CATEGORIES};seen=set()
    def scan(fd,relative,device,depth=0):
        if depth>64:raise RuntimeError('学习空间目录层级过深，无法安全统计')
        with os.scandir(fd) as entries:
            for entry in entries:
                try:
                    info=os.stat(entry.name,dir_fd=fd,follow_symlinks=False)
                    if info.st_dev!=device or stat.S_ISLNK(info.st_mode):continue
                    path=relative+'/'+entry.name if relative else entry.name
                    if not relative and entry.name not in PARTS:continue
                    if stat.S_ISDIR(info.st_mode):
                        child=os.open(entry.name,FLAGS,dir_fd=fd)
                        try:
                            if os.fstat(child).st_dev==device:scan(child,path,device,depth+1)
                        finally:os.close(child)
                    elif stat.S_ISREG(info.st_mode) and (info.st_dev,info.st_ino) not in seen:
                        seen.add((info.st_dev,info.st_ino));sizes[category(path)]+=info.st_size
                except (FileNotFoundError,NotADirectoryError):continue
                except OSError as error:
                    if error.errno==errno.ELOOP:continue
                    raise
    # The platform-owned account boundary is 0711, intentionally not listable
    # by the worker. Open only the known private child directories.
    for part in sorted(PARTS):
        try:descriptor=os.open(root/part,FLAGS)
        except FileNotFoundError:continue
        try:
            device=root.stat().st_dev
            if os.fstat(descriptor).st_dev!=device:raise RuntimeError('个人空间挂载位置发生变化，无法安全统计')
            scan(descriptor,part,device)
        finally:os.close(descriptor)
    used=sum(sizes.values())
    return {'usedBytes':used,'quotaBytes':INITIAL_STORAGE_BYTES,'initialQuotaBytes':INITIAL_STORAGE_BYTES,
        'remainingBytes':max(0,INITIAL_STORAGE_BYTES-used),'percent':min(100,used*100/INITIAL_STORAGE_BYTES),
        'categories':[{'key':key,'label':label,'bytes':sizes[key]} for key,label in CATEGORIES],
        'asOf':int(time.time()*1000)}


def ensure_capacity(root,extra_bytes=0):
    current=snapshot(root)
    if current['usedBytes']>=current['quotaBytes'] or current['usedBytes']+max(0,int(extra_bytes))>current['quotaBytes']:
        raise StorageQuotaExceeded()
    return current


def version(info):return f'{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}'


@contextmanager
def parent_descriptor(root,relative):
    path=PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(p in {'.','..',''} for p in str(relative).split('/')) or path.parts[0] not in PARTS:
        raise ValueError('只能管理当前账号的学习空间')
    fd=os.open(root,getattr(os,'O_PATH',os.O_RDONLY)|os.O_DIRECTORY|os.O_NOFOLLOW);device=os.fstat(fd).st_dev
    try:
        for part in path.parts[:-1]:
            child=os.open(part,FLAGS,dir_fd=fd)
            if os.fstat(child).st_dev!=device:
                os.close(child);raise ValueError('不能跨挂载点访问')
            os.close(fd);fd=child
        yield fd,path.name
    finally:os.close(fd)


def open_file(root,relative):
    with parent_descriptor(root,relative) as (parent,name):
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):os.close(fd);raise ValueError('请选择普通文件')
        return fd,info


def remove_file(root,relative,expected):
    if PurePosixPath(relative).parts[0] not in {'workspace','tmp'}:raise ValueError('资料和学习记录请使用对应的删除操作')
    with parent_descriptor(root,relative) as (parent,name):
        info=os.stat(name,dir_fd=parent,follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or version(info)!=expected:raise ValueError('文件已变化，请刷新后再删除')
        os.unlink(name,dir_fd=parent)
