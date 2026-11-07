const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync('learning_ext/assets/server_session.js','utf8');
const origin='https://learn.example';
const prefix='/official/learn-everything/';
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
function harness(handler){
  const values=new Map([['aethericai-community-access-token','token-a'],['aethericai-community-refresh-token','refresh-a']]);
  const calls=[],events={},nodes=new Map();let reloads=0,inert=false;
  class Element{
    constructor(tag){this.tag=tag;this.children=[];this.style={};this.attributes={};}
    setAttribute(k,v){this.attributes[k]=v;}
    append(...items){this.children.push(...items);for(const e of items)if(e.id)nodes.set(e.id,e);}
    querySelector(tag){return this.children.find(x=>x.tag===tag);}
    remove(){nodes.delete(this.id);}
  }
  class EventSource{constructor(url){this.url=url;this.closed=false;}close(){this.closed=true;}}
  class XHR{open(method,url){this.url=url;}setRequestHeader(k,v){this.headers??={};this.headers[k]=v;}addEventListener(){}send(){this.sent=true;}}
  const context={URL,Request,Headers,Response,DOMException,AbortController,console,
    localStorage:{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)},
    location:{origin,pathname:prefix,href:origin+prefix+'?ticket=fixture',reload(){reloads++;}},
    history:{state:null,replaceState(){}},setInterval:()=>1,clearInterval(){},EventSource,XMLHttpRequest:XHR,
    document:{hidden:false,body:new Element('body'),createElement:tag=>new Element(tag),getElementById:id=>nodes.get(id),
      querySelector:selector=>selector==='gradio-app'?{setAttribute(){inert=true;}}:null,querySelectorAll:()=>[],
      addEventListener:(name,fn)=>{events[name]=fn;},removeEventListener(){}},
    addEventListener:(name,fn)=>{events[name]=fn;},removeEventListener(){},__LE_ACCOUNT_ID__:'owner-a'};
  context.window=context;
  context.fetch=async(input,init)=>{
    const request=input instanceof Request?input:new Request(new URL(String(input),origin),init);
    calls.push({path:new URL(request.url).pathname,headers:request.headers,url:request.url});
    if(handler){const reply=await handler(request);if(reply)return reply;}
    if(request.url.endsWith('/me'))return new Response(JSON.stringify({userId:'owner-a'}));
    if(request.url.endsWith('/entry'))return new Response(JSON.stringify({url:prefix+'?ticket=fixture'}));
    return new Response('{}');
  };
  vm.runInNewContext(source,context);
  return {context,values,calls,events,nodes,get inert(){return inert;},get reloads(){return reloads;}};
}
test('every worker fetch and stream is bound to the rendered account',async()=>{
 const h=harness();await settle();
 await h.context.fetch(new Request(origin+prefix+'queue/join',{method:'POST',body:'{}'}));
 assert.equal(h.calls.at(-1).headers.get('X-Learn-Expected-User'),'owner-a');
 const stream=new h.context.EventSource(prefix+'queue/data?session_hash=fixture');
 assert.equal(new URL(stream.url).searchParams.get('__le_owner'),'owner-a');
 const xhr=new h.context.XMLHttpRequest();xhr.open('POST',prefix+'upload');xhr.send('file');
 assert.equal(xhr.headers['X-Learn-Expected-User'],'owner-a');
 assert.equal(h.calls.filter(x=>x.path.endsWith('/me'))[0].headers.get('X-Learn-Expected-User'),null);
});
test('another tab login cannot silently renew or route the old document',async()=>{
 const h=harness(request=>request.headers.get('authorization')==='Bearer token-b'?new Response(JSON.stringify({userId:'owner-b'})):null);
 await settle();h.calls.length=0;h.values.set('aethericai-community-access-token','token-b');
 h.events.storage({key:'aethericai-community-access-token'});await settle();
 assert.equal(h.calls.filter(x=>x.path.endsWith('/entry')).length,0);assert(h.inert);
 await assert.rejects(h.context.fetch(origin+prefix+'config'),{name:'AbortError'});
 assert.match(h.nodes.get('le-session-notice').querySelector('p').textContent,/账号已变化/);
});
test('cookie mismatch stops the old document and closes its SSE stream',async()=>{
 const h=harness(request=>request.url.endsWith('/config')?new Response('{}',{status:409,headers:{'X-Learn-Error':'ACCOUNT_CHANGED'}}):null);
 await settle();const stream=new h.context.EventSource(prefix+'queue/data');
 await assert.rejects(h.context.fetch(origin+prefix+'config'),{name:'AbortError'});assert(stream.closed);assert(h.inert);
});
test('an old refresh cannot overwrite a new login',async()=>{
 let release;const pending=new Promise(resolve=>release=resolve);
 const h=harness(async request=>{
  if(request.url.endsWith('/me'))return request.headers.get('authorization')==='Bearer new-login'?new Response(JSON.stringify({userId:'owner-b'})):new Response('{}',{status:401});
  if(request.url.endsWith('/refresh')){await pending;return new Response(JSON.stringify({accessToken:'old-refreshed',refreshToken:'old-refresh'}));}
 });
 await settle();h.values.set('aethericai-community-access-token','new-login');release();await settle();
 assert.equal(h.values.get('aethericai-community-access-token'),'new-login');assert(h.inert);
 assert.equal(h.calls.filter(x=>x.path.endsWith('/entry')).length,0);
});
test('same-account refresh in another tab does not discard saved workspace state',async()=>{
 const h=harness();await settle();h.values.set('aethericai-community-access-token','same-owner-new-token');
 h.events.storage({key:'aethericai-community-access-token'});await settle();
 assert.equal(h.inert,false);assert.equal(h.nodes.has('le-session-notice'),false);
 await h.context.fetch(origin+prefix+'config');
 assert.equal(h.calls.at(-1).headers.get('X-Learn-Expected-User'),'owner-a');
});
test('logout stops requests and restoring browser history reloads the document',async()=>{
 const h=harness();await settle();h.values.delete('aethericai-community-access-token');h.events.storage({key:null});
 await assert.rejects(h.context.fetch(origin+prefix+'queue/join'),{name:'AbortError'});
 h.events.pageshow({persisted:true});assert.equal(h.reloads,1);
});
