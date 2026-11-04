(() => {
  if (!window.location.pathname.startsWith('/official/learn-everything/')) return;
  const ACCESS='aethericai-community-access-token', REFRESH='aethericai-community-refresh-token';
  let active=false, stopped=false;
  const controller=new AbortController();
  const call=(path,token,body={})=>fetch('/official-api'+path,{method:'POST',credentials:'include',signal:controller.signal,
    headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},body:JSON.stringify(body)});
  async function renew(){
    if(active||stopped||document.hidden)return;
    active=true;
    try{
      let token=localStorage.getItem(ACCESS);
      if(!token)return;
      let response=await call('/api/v1/console/learn-everything/entry',token);
      if(response.status===401&&localStorage.getItem(REFRESH)){
        const refreshed=await call('/api/v1/auth/refresh',null,{refreshToken:localStorage.getItem(REFRESH)});
        if(refreshed.ok){
          const session=await refreshed.json();
          localStorage.setItem(ACCESS,session.accessToken);localStorage.setItem(REFRESH,session.refreshToken);
          localStorage.setItem('aethericai-community-access-expires',String(session.accessTokenExpiresAtEpochMs));
        }
        token=localStorage.getItem(ACCESS);
        response=await call('/api/v1/console/learn-everything/entry',token);
      }
      if(!response.ok){
        if(response.status===401||response.status===403){
          let notice=document.getElementById('le-session-notice');
          if(!notice){notice=document.createElement('p');notice.id='le-session-notice';notice.setAttribute('role','alert');
            notice.style.cssText='position:fixed;bottom:16px;right:16px;z-index:2000;padding:16px;background:var(--le-surface,#fff);border:1px solid var(--le-line,#ddd);border-radius:12px';
            const link=document.createElement('a');link.href='/official/products/learn-everything/';link.textContent='登录或产品资格已过期，请从官网重新进入';notice.append(link);document.body.append(notice);}
        }
        return;
      }
      const entry=await response.json();
      const url=new URL(entry.url,location.origin);
      if(url.origin!==location.origin||url.pathname!=='/official/learn-everything/')return;
      await fetch(url,{credentials:'include',signal:controller.signal});
      document.getElementById('le-session-notice')?.remove();
    }catch(error){if(error.name!=='AbortError')console.warn('学习工作台连接暂时中断，将自动重试。');}
    finally{active=false;}
  }
  const url=new URL(location.href);url.searchParams.delete('ticket');history.replaceState(history.state,'',url);
  const timer=setInterval(renew,120000);document.addEventListener('visibilitychange',renew);
  window.addEventListener('pagehide',()=>{stopped=true;clearInterval(timer);controller.abort();document.removeEventListener('visibilitychange',renew);},{once:true});
})();
