(() => {
  const base=(window.__LE_ROOT_PATH__||'')+'/platform/storage';
  let mounted=false;
  const colors=['#376a9d','#4a9c9d','#8b87c5','#86adcc','#c8a66b','#a6b2bd'];
  const bytes=value=>value<1024?`${value} B`:value<1024**2?`${(value/1024).toFixed(1)} KB`:value<1024**3?`${(value/1024**2).toFixed(1)} MB`:`${(value/1024**3).toFixed(2)} GB`;
  async function start(){
    const root=document.getElementById('le-storage-root');if(!root||mounted)return;mounted=true;
    let pageIndex=0,accountId=null,items=[],batch=false,selection=new Set(),pending=null,busy=false;
    const status=root.querySelector('[data-storage-status]'),list=root.querySelector('[data-storage-list]'),dialog=root.querySelector('dialog');
    const identity=item=>JSON.stringify([item.kind,item.index,item.id,item.path,item.version]);
    const message=(text,error=false)=>{status.textContent=text;status.dataset.error=String(error);};
    async function call(path,body){
      const response=await fetch(base+path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',
        headers:body?{'Content-Type':'application/json'}:{},...(body?{body:JSON.stringify(body)}:{})});
      if(!response.ok){let result;try{result=await response.json();}catch{}throw Error(result?.detail||'暂时无法读取空间，请稍后重试。');}
      return response;
    }
    const visible=()=>items.filter(item=>(root.querySelector('select').value==='all'||item.kind===root.querySelector('select').value)&&item.name.toLowerCase().includes(root.querySelector('input[type=search]').value.toLowerCase()));
    function render(){
      list.replaceChildren();const filtered=visible();pageIndex=Math.min(pageIndex,Math.max(0,Math.ceil(filtered.length/20)-1));const rows=filtered.slice(pageIndex*20,pageIndex*20+20);root.querySelector('[data-storage-empty]').hidden=rows.length>0;
      root.querySelector('[data-storage-page]').textContent=`共 ${filtered.length} 项 · 第 ${pageIndex+1} / ${Math.max(1,Math.ceil(filtered.length/20))} 页`;root.querySelector('[data-storage-prev]').disabled=pageIndex===0;root.querySelector('[data-storage-next]').disabled=(pageIndex+1)*20>=filtered.length;
      for(const item of rows){
        const row=document.createElement('div');row.className='le-storage-row';
        const icon=document.createElement('span');icon.className='le-storage-file-icon';icon.textContent=item.kind==='project'?'▤':item.kind==='conversation'?'◌':'▧';icon.setAttribute('aria-hidden','true');
        const title=document.createElement('div');title.className='le-storage-file-name';const name=document.createElement('strong');name.textContent=item.name;const detail=document.createElement('small');detail.textContent=item.label;title.append(name,detail);
        const size=document.createElement('span');size.className='le-storage-file-size';size.textContent=typeof item.bytes==='number'?bytes(item.bytes):'学习记录';
        const actions=document.createElement('details');actions.className='le-storage-actions';const more=document.createElement('summary');more.textContent='⋯';more.setAttribute('aria-label',`更多操作：${item.name}`);
        const menu=document.createElement('div');const download=document.createElement('button');download.type='button';download.textContent='下载';download.className='le-storage-download';download.addEventListener('click',()=>{actions.open=false;downloadItems([item]);});
        const remove=document.createElement('button');remove.type='button';remove.textContent='删除';remove.className='le-storage-delete';remove.addEventListener('click',()=>{actions.open=false;pending=item;root.querySelector('[data-storage-delete-name]').textContent=item.name;dialog.showModal();});
        menu.append(download,remove);actions.append(more,menu);row.append(icon,title,size,actions);
        if(batch){const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.setAttribute('aria-label',`选择 ${item.name}`);checkbox.checked=selection.has(identity(item));checkbox.addEventListener('change',()=>{if(checkbox.checked)selection.add(identity(item));else selection.delete(identity(item));});row.append(checkbox);}
        list.append(row);
      }
      root.querySelector('[data-storage-selection]').hidden=!batch;
      root.querySelector('[data-storage-batch]').textContent=batch?'退出批量下载':'批量下载';
    }
    async function refresh(){
      if(busy)return;busy=true;message('正在读取个人空间…');
      try{
        const result=await(await call('')).json();const usage=result.storage;accountId=result.accountId;items=result.items;
        const existing=new Set(items.map(identity));selection=new Set([...selection].filter(key=>existing.has(key)));
        root.querySelector('[data-storage-used]').textContent=bytes(usage.usedBytes);
        root.querySelector('[data-storage-remaining]').textContent=`剩余 ${bytes(usage.remainingBytes)}`;
        const meter=root.querySelector('.le-storage-meter');meter.setAttribute('aria-valuenow',String(usage.percent));meter.setAttribute('aria-valuetext',`${bytes(usage.usedBytes)} / 5 GB`);meter.firstElementChild.style.width=usage.percent+'%';
        const parts=root.querySelector('.le-storage-parts'),legend=root.querySelector('[data-storage-categories]');parts.replaceChildren();legend.replaceChildren();
        usage.categories.forEach((category,index)=>{const portion=document.createElement('span');portion.style.width=(usage.usedBytes?category.bytes*100/usage.usedBytes:0)+'%';portion.style.background=colors[index];parts.append(portion);const item=document.createElement('li');const dot=document.createElement('i');dot.style.background=colors[index];const label=document.createElement('span');label.textContent=category.label;const size=document.createElement('strong');size.textContent=bytes(category.bytes);item.append(dot,label,size);legend.append(item);});
        render();message(usage.remainingBytes===0?'个人学习空间已满，请下载或删除内容后继续。':'用量已更新。',usage.remainingBytes===0);
      }catch(error){message(error.message,true);}finally{busy=false;}
    }
    async function downloadItems(chosen){
      if(!chosen.length){message('请先选择要下载的项目。',true);return;}
      message('正在准备下载…');
      try{const response=await call('/download',{items:chosen,expectedAccount:accountId});const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;let name='学习空间.zip';const header=response.headers.get('Content-Disposition')||'';const match=header.match(/filename\*=UTF-8''([^;]+)/i);if(match)name=decodeURIComponent(match[1]);link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);message('下载已开始。');}catch(error){message(error.message,true);}
    }
    root.querySelector('[data-storage-refresh]').addEventListener('click',refresh);
    root.querySelector('input[type=search]').addEventListener('input',()=>{pageIndex=0;render();});root.querySelector('select').addEventListener('change',()=>{pageIndex=0;render();});
    for(const [key,delta] of [['prev',-1],['next',1]])root.querySelector(`[data-storage-${key}]`).addEventListener('click',()=>{pageIndex+=delta;if(batch)selection=new Set(visible().slice(pageIndex*20,pageIndex*20+20).map(identity));render();});
    root.querySelector('[data-storage-batch]').addEventListener('click',()=>{batch=!batch;if(batch)selection=new Set(visible().slice(pageIndex*20,pageIndex*20+20).map(identity));render();});
    root.querySelector('[data-storage-none]').addEventListener('click',()=>{selection.clear();render();});root.querySelector('[data-storage-all]').addEventListener('click',()=>{selection=new Set(visible().slice(pageIndex*20,pageIndex*20+20).map(identity));render();});
    root.querySelector('[data-storage-download-selected]').addEventListener('click',()=>downloadItems(items.filter(item=>selection.has(identity(item)))));
    root.querySelector('[data-storage-cancel]').addEventListener('click',()=>dialog.close());
    root.querySelector('[data-storage-confirm-delete]').addEventListener('click',async()=>{if(!pending)return;const button=root.querySelector('[data-storage-confirm-delete]');button.disabled=true;try{await call('/delete',{item:pending,confirm:true,expectedAccount:accountId});dialog.close();message('已删除。');await refresh();}catch(error){dialog.close();message(error.message,true);}finally{button.disabled=false;pending=null;}});
    document.getElementById('learning-storage-tab-button')?.addEventListener('click',refresh);
    await refresh();
  }
  const observer=new MutationObserver(()=>{if(document.getElementById('le-storage-root')){observer.disconnect();start();}});observer.observe(document.documentElement,{childList:true,subtree:true});start();
})();
