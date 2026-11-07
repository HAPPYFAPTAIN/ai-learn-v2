(() => {
  const PREFIX='/official/learn-everything/';
  if (!location.pathname.startsWith(PREFIX)) return;
  const OWNER=window.__LE_ACCOUNT_ID__;
  if (!OWNER) return;
  const ACCESS='aethericai-community-access-token', REFRESH='aethericai-community-refresh-token';
  const nativeFetch=window.fetch.bind(window);
  let active=false, stopped=false, retryRenew=false, timer;
  const controller=new AbortController();
  const streams=new Set();
  const isLearning=url=>url.origin===location.origin&&url.pathname.startsWith(PREFIX);
  const changedMessage='登录账号已变化，请从官网重新打开学习工作台。已有路线仍保存在原账号。';
  function notice(message,block=false){
    const show=()=>{
      let box=document.getElementById('le-session-notice');
      if(!box){box=document.createElement('div');box.id='le-session-notice';box.setAttribute('role','alert');
        box.style.cssText='position:fixed;inset:auto 16px 16px auto;max-width:460px;z-index:9999;padding:20px;background:var(--le-surface,#fff);color:var(--le-ink,#152535);border:1px solid var(--le-line,#aaa);border-radius:12px';
        const text=document.createElement('p');box.append(text);
        const link=document.createElement('a');link.href='/official/products/learn-everything/';link.textContent='从官网重新进入';box.append(link);document.body.append(box);}
      box.querySelector('p').textContent=message;
      if(block){
        document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
        document.querySelector('gradio-app')?.setAttribute('inert','');
        document.body.setAttribute('data-le-account-stopped','');
        if(!document.getElementById('le-session-stop-style')){
          const style=document.createElement('style');style.id='le-session-stop-style';
          style.textContent='body[data-le-account-stopped] gradio-app{display:none!important}';document.body.append(style);
        }
        box.style.inset='24px 16px auto';
      }
    };
    if(document.body)show();else document.addEventListener('DOMContentLoaded',show,{once:true});
  }
  function stop(message){
    if(stopped)return;
    stopped=true;clearInterval(timer);controller.abort();
    for(const stream of streams)stream.close();streams.clear();
    notice(message,true);
  }
  function checkReply(response){
    if(response.status===409&&response.headers.get('X-Learn-Error')==='ACCOUNT_CHANGED')stop(changedMessage);
    return response;
  }
  // Bind every Gradio fetch to the account that rendered this document. A shared
  // browser cookie may change in another tab; an old session must never follow it.
  window.fetch=(input,init)=>{
    const url=new URL(input instanceof Request?input.url:String(input),location.origin);
    if(!isLearning(url))return nativeFetch(input,init);
    if(stopped)return Promise.reject(new DOMException('Learning account changed','AbortError'));
    const request=new Request(input,init),headers=new Headers(request.headers);
    headers.set('X-Learn-Expected-User',OWNER);
    return nativeFetch(new Request(request,{headers})).then(response=>{
      checkReply(response);
      if(stopped)throw new DOMException('Learning account changed','AbortError');
      return response;
    });
  };
  if(window.XMLHttpRequest){
    const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open=function(method,input,...args){
      this.__leLearningRequest=isLearning(new URL(String(input),location.origin));
      return open.call(this,method,input,...args);
    };
    XMLHttpRequest.prototype.send=function(...args){
      if(this.__leLearningRequest){
        if(stopped)throw new DOMException('Learning account changed','AbortError');
        this.setRequestHeader('X-Learn-Expected-User',OWNER);
        this.addEventListener('load',()=>{if(this.status===409&&this.getResponseHeader('X-Learn-Error')==='ACCOUNT_CHANGED')stop(changedMessage);});
      }
      return send.apply(this,args);
    };
  }
  // EventSource has no header option, so bind its queue URL explicitly too.
  if(window.EventSource){
    const Original=window.EventSource;
    window.EventSource=class extends Original{
      constructor(input,options){
        const url=new URL(String(input),location.origin);
        if(isLearning(url))url.searchParams.set('__le_owner',OWNER);
        super(url.href,options);streams.add(this);
        if(stopped)this.close();
      }
      close(){streams.delete(this);super.close();}
    };
  }
  const call=(path,token,body)=>nativeFetch('/official-api'+path,{
    method:body===undefined?'GET':'POST',credentials:'include',signal:controller.signal,
    headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  async function renew(){
    if(active||stopped||document.hidden)return;
    active=true;
    try{
      let token=localStorage.getItem(ACCESS);
      if(!token)return;
      let profile=await call('/api/v1/console/me',token);
      if(profile.status===401&&localStorage.getItem(REFRESH)){
        const refreshed=await call('/api/v1/auth/refresh',null,{refreshToken:localStorage.getItem(REFRESH)});
        if(!refreshed.ok){stop('登录已过期，请重新进入。');return;}
        const session=await refreshed.json();
        // A newer login must not be overwritten by an older refresh response.
        if(localStorage.getItem(ACCESS)!==token){retryRenew=true;return;}
        localStorage.setItem(ACCESS,session.accessToken);localStorage.setItem(REFRESH,session.refreshToken);
        localStorage.setItem('aethericai-community-access-expires',String(session.accessTokenExpiresAtEpochMs));
        token=session.accessToken;profile=await call('/api/v1/console/me',token);
      }
      if(!profile.ok){if(profile.status===401||profile.status===403)stop('登录已过期，请重新进入。');return;}
      if((await profile.json()).userId!==OWNER){stop(changedMessage);return;}
      if(localStorage.getItem(ACCESS)!==token){retryRenew=true;return;}
      const response=await call('/api/v1/console/learn-everything/entry',token,{});
      if(!response.ok){if(response.status===401||response.status===403)stop('登录或产品资格已过期，请重新进入。');return;}
      const entry=await response.json(),url=new URL(entry.url,location.origin);
      if(!isLearning(url)||url.pathname!==PREFIX)return;
      if(stopped)return;
      if(localStorage.getItem(ACCESS)!==token){retryRenew=true;return;}
      const accepted=await window.fetch(url,{credentials:'include',signal:controller.signal});
      if(accepted.ok)document.getElementById('le-session-notice')?.remove();
    }catch(error){if(error.name!=='AbortError')console.warn('学习工作台连接暂时中断，将自动重试。');}
    finally{
      active=false;
      if(retryRenew&&!stopped){retryRenew=false;Promise.resolve().then(renew);}
    }
  }
  const url=new URL(location.href);url.searchParams.delete('ticket');history.replaceState(history.state,'',url);
  const storageChanged=event=>{
    if(event.key===ACCESS||event.key===null){
      if(!localStorage.getItem(ACCESS))stop('你已退出官网，请重新登录后进入。');
      else if(active)retryRenew=true;
      else renew();
    }
  };
  const visible=()=>{if(!stopped)renew();};
  timer=setInterval(renew,120000);
  window.addEventListener('storage',storageChanged);document.addEventListener('visibilitychange',visible);
  window.addEventListener('pagehide',()=>{stopped=true;clearInterval(timer);controller.abort();for(const stream of streams)stream.close();document.removeEventListener('visibilitychange',visible);window.removeEventListener('storage',storageChanged);},{once:true});
  // A restored document may still contain another account's data and state.
  window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
  renew();
})();
