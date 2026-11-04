"""Account-bound storage UI APIs; reuse the product's real record operations."""
import asyncio
from contextlib import contextmanager
import io
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import threading
from urllib.parse import quote
import zipfile

from fastapi import HTTPException,Request
from fastapi.responses import FileResponse,StreamingResponse
from starlette.background import BackgroundTask
from le_platform import storage

ASSETS=Path(__file__).parent/'assets'


def register(app,learning):
    root=Path(os.environ['LE_WORKER_ROOT'])
    download_slot=threading.Lock()
    platform_images={}
    release=Path(os.environ['LE_PLATFORM_RELEASE'])
    for folder in [release/'source/learning_ext/assets',release/'source/kotaemon/libs/ktem/ktem/assets']:
        for asset in folder.rglob('*'):
            if asset.is_file() and asset.suffix.lower() in {'.png','.svg','.ico','.jpg','.webp'}:
                platform_images.setdefault(asset.name,set()).add((asset.stat().st_size,hashlib.sha256(asset.read_bytes()).digest()))

    async def request_body(request):
        try:body=await request.json()
        except (ValueError,UnicodeError):raise HTTPException(400,'请求格式无效') from None
        if not isinstance(body,dict):raise HTTPException(400,'请求格式无效')
        return body

    def expected_account(body):
        if body.get('expectedAccount')!=os.environ['LE_OFFICIAL_USER']:
            raise HTTPException(409,'登录账号已变化，请刷新空间管理后重试。')

    def index_for(value):
        return next(index for index in learning.index_manager.indices if str(index.id)==str(value))

    def source_for(item):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from ktem.db.engine import engine
        index=index_for(item.get('index'));Source=index._resources['Source']
        with Session(engine) as session:
            row=session.execute(select(Source).where(Source.id==str(item['id']),Source.user=='default')).scalar_one_or_none()
            if row is None:raise ValueError('资料已不存在，请刷新')
            path=(Path(index._fs_path)/row.path).resolve()
            relative=str(path.relative_to(root.resolve()))
            return index,row,relative

    def catalogue():
        from sqlmodel import Session,select
        from ktem.db.engine import engine
        from ktem.db.models import Conversation
        from learning_ext.db.models import LearningProject
        items=[]
        with Session(engine) as session:
            for project in session.exec(select(LearningProject).where(LearningProject.user_id=='default')).all():
                items.append({'kind':'project','id':str(project.id),'name':project.title or project.topic,'label':'课程与学习记录'})
            for conversation in session.exec(select(Conversation).where(Conversation.user=='default')).all():
                items.append({'kind':'conversation','id':conversation.id,'name':conversation.name,'label':'问答记录'})
            for index in learning.index_manager.indices:
                Source=index._resources['Source']
                for row in session.exec(select(Source).where(Source.user=='default')).all():
                    items.append({'kind':'source','id':str(row.id),'index':str(index.id),'name':row.name,'bytes':row.size,'label':'资料文件'})
        for folder in ['workspace','tmp/gradio']:
            directory=root/folder
            if not directory.exists():continue
            for current,dirs,files in os.walk(directory,followlinks=False):
                dirs[:]=[name for name in dirs if not (Path(current)/name).is_symlink()]
                for name in files:
                    path=Path(current)/name
                    try:
                        info=path.lstat()
                        if not stat.S_ISREG(info.st_mode):continue
                        if folder=='tmp/gradio':
                            if info.st_size==0 and path.parent==directory and name.startswith('tmp'):continue
                            images=platform_images.get(name,set())
                            if any(size==info.st_size for size,_ in images):
                                fd,current_info=storage.open_file(root,str(path.relative_to(root)))
                                try:signature=hashlib.sha256(os.read(fd,info.st_size+1)).digest()
                                finally:os.close(fd)
                                if storage.version(current_info)==storage.version(info) and (info.st_size,signature) in images:continue
                        items.append({'kind':'file','path':str(path.relative_to(root)),'name':name,'bytes':info.st_size,
                            'version':storage.version(info),'label':'个人文件' if folder=='workspace' else '临时附件'})
                    except FileNotFoundError:continue
                    if len(items)>=1000:return items
        return items

    @contextmanager
    def exclusive_cleanup():
        from learning_ext.llm.client import _REQUEST_SLOT
        from learning_ext.progress.prep import has_pending
        if not _REQUEST_SLOT.acquire(blocking=False):raise HTTPException(409,'正在生成内容，请结束后再清理空间。')
        try:
            if has_pending():raise HTTPException(409,'正在准备课程，完成后再清理空间。')
            yield
        finally:_REQUEST_SLOT.release()

    def compact():
        from ktem.db.engine import engine
        with sqlite3.connect(engine.url.database,timeout=10,isolation_level=None) as db:db.execute('VACUUM')

    def exported(item):
        kind=item.get('kind')
        if kind=='source':
            _,row,relative=source_for(item);fd,info=storage.open_file(root,relative)
            return row.name,fd,info.st_size
        if kind=='file':
            relative=str(item['path'])
            if relative.split('/')[0] not in {'workspace','tmp'}:raise ValueError('请选择个人文件或附件')
            fd,info=storage.open_file(root,relative)
            if storage.version(info)!=item.get('version'):os.close(fd);raise ValueError('文件已变化，请刷新')
            return Path(relative).name,fd,info.st_size
        from sqlmodel import Session
        from ktem.db.engine import engine
        with Session(engine) as session:
            if kind=='project':
                from learning_ext.db.models import LearningProject
                from learning_ext.exporter.service import export_markdown
                project=session.get(LearningProject,int(item['id']))
                if project is None or project.user_id!='default':raise ValueError('课程不可用')
                content=export_markdown(session,project.id).encode();name=(project.title or '课程')+'.md'
            elif kind=='conversation':
                from ktem.db.models import Conversation
                row=session.get(Conversation,str(item['id']))
                if row is None or row.user!='default':raise ValueError('记录不可用')
                content=json.dumps({'title':row.name,'data':row.data_source},ensure_ascii=False,indent=2).encode();name='问答记录.json'
            else:raise ValueError('不支持的项目类型')
        return name,io.BytesIO(content),len(content)

    @app.get('/platform/storage/assets/{name}')
    def asset(name:str):
        if name not in {'storage.js','storage.css'}:raise HTTPException(404)
        return FileResponse(ASSETS/name)

    @app.get('/platform/storage')
    def usage():return {'accountId':os.environ['LE_OFFICIAL_USER'],'storage':storage.snapshot(root),'items':catalogue()}

    @app.post('/platform/storage/download')
    async def download(request:Request):
        body=await request_body(request);expected_account(body);items=body.get('items',[])
        if not isinstance(items,list) or not 1<=len(items)<=100:raise HTTPException(400,'请选择1至100项')
        if not download_slot.acquire(blocking=False):raise HTTPException(429,'已有下载正在准备，请等待当前下载结束。')
        handles=[];staging=None
        released=False
        def close():
            nonlocal handles,released
            for _,entry,_ in handles:
                os.close(entry) if isinstance(entry,int) else entry.close()
            handles=[]
            if staging:staging.unlink(missing_ok=True)
            if not released:released=True;download_slot.release()
        try:
            for item in items:
                if not isinstance(item,dict):raise ValueError('文件选择无效')
                name,handle,size=exported(item)
                handles.append((Path(name).name,handle,size))
            if len(handles)>1:
                if sum(size for _,_,size in handles)>512*1024**2:raise ValueError('批量下载请控制在512 MB以内，较大文件可单独下载')
                stage=root/'downloads'
                descriptor,path=tempfile.mkstemp(prefix='batch-',suffix='.zip',dir=stage);os.close(descriptor);staging=Path(path)
                with zipfile.ZipFile(staging,'w',compression=zipfile.ZIP_STORED) as archive:
                    for number,(name,handle,_) in enumerate(handles,1):
                        with archive.open(f'{number:03d}-{name}','w') as target:
                            if isinstance(handle,int):
                                while chunk:=os.read(handle,65536):
                                    target.write(chunk);await asyncio.sleep(0)
                            else:
                                while chunk:=handle.read(65536):
                                    target.write(chunk);await asyncio.sleep(0)
                original=handles;handles=[]
                for _,handle,_ in original:os.close(handle) if isinstance(handle,int) else handle.close()
                handles=[('学习空间.zip',os.open(staging,os.O_RDONLY|os.O_NOFOLLOW),staging.stat().st_size)]
            name,handle,_=handles[0]
            def stream():
                try:
                    if isinstance(handle,int):
                        while chunk:=os.read(handle,65536):yield chunk
                    else:yield from iter(lambda:handle.read(65536),b'')
                finally:close()
            return StreamingResponse(stream(),media_type='application/octet-stream',
                headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(name),'Cache-Control':'no-store'},background=BackgroundTask(close))
        except BaseException as error:
            close()
            if not isinstance(error,(ValueError,KeyError,StopIteration,OSError)):raise
            raise HTTPException(409,str(error) if isinstance(error,ValueError) else '文件不可用，请刷新后重试') from None

    @app.post('/platform/storage/delete')
    async def delete(request:Request):
        body=await request_body(request);expected_account(body);item=body.get('item')
        if body.get('confirm') is not True or not isinstance(item,dict):raise HTTPException(400,'请确认要永久删除的项目')
        def perform():
            from sqlmodel import Session
            from ktem.db.engine import engine
            with exclusive_cleanup():
                kind=item.get('kind')
                if kind=='file':storage.remove_file(root,str(item['path']),str(item.get('version','')))
                elif kind=='source':
                    index,row,relative=source_for(item)
                    # Reuse upstream index/vector/document deletion; then remove its orphaned original.
                    getattr(learning,f'_index_{index.id}').delete_event(row.id)
                    from sqlalchemy import select
                    with Session(engine) as session:
                        shared=session.exec(select(index._resources['Source']).where(index._resources['Source'].path==row.path)).first()
                    if shared is None:
                        with storage.parent_descriptor(root,relative) as (parent,name):
                            if stat.S_ISREG(os.stat(name,dir_fd=parent,follow_symlinks=False).st_mode):os.unlink(name,dir_fd=parent)
                elif kind=='project':
                    from learning_ext.db.models import LearningProject
                    from learning_ext.project_ops import delete_project
                    with Session(engine) as session:
                        project=session.get(LearningProject,int(item['id']))
                        if project is None or project.user_id!='default':raise ValueError('课程已变化，请刷新')
                        delete_project(session,project.id)
                elif kind=='conversation':
                    from ktem.db.models import Conversation
                    with Session(engine) as session:
                        row=session.get(Conversation,str(item['id']))
                        if row is None or row.user!='default':raise ValueError('问答记录已变化，请刷新')
                    learning.chat_page.chat_control.delete_conv(str(item['id']),'default')
                else:raise ValueError('不能删除系统数据库，请选择具体资料或记录')
                compacted=True
                if kind in {'source','project','conversation'}:
                    try:compact()
                    except sqlite3.OperationalError:compacted=False
                return compacted
        try:compacted=await asyncio.to_thread(perform)
        except (ValueError,KeyError,StopIteration,OSError) as error:raise HTTPException(409,str(error) if isinstance(error,ValueError) else '项目已变化，请刷新') from None
        return {'deleted':True,'compacted':compacted,'storage':await asyncio.to_thread(storage.snapshot,root)}
