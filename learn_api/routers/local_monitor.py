"""Loopback-only development monitor; excluded from the public API schema."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from learn_api.errors import ApiError
from learn_core import monitoring

router = APIRouter(tags=["local-monitor"])

_PAGE = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Learn 本地性能监控</title>
<style>
:root{color-scheme:dark;background:#0b1118;color:#e5edf5;font:14px/1.5 system-ui,sans-serif}body{max-width:1180px;margin:0 auto;padding:28px}h1{font-size:24px}h2{font-size:15px;margin:0 0 12px}.muted{color:#91a1b2}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.card{background:#131d28;border:1px solid #263646;border-radius:12px;padding:16px}.metric{font-size:24px;font-weight:650}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{text-align:left;padding:8px;border-bottom:1px solid #263646}th{color:#91a1b2;font-weight:500}button{background:#193b36;color:#b8f5df;border:1px solid #2c685d;border-radius:8px;padding:8px 14px;cursor:pointer}.ok{color:#7de2ba}.bad{color:#ffb4a8}code{word-break:break-all}@media(max-width:600px){body{padding:16px}.grid{grid-template-columns:1fr}}
</style>
<h1>AI Learn 本地性能监控</h1>
<p class="muted">仅当前开发进程 · 每 5 秒刷新 · 不保存对话、票据或密钥。SSE 只统计连接和订阅，不记录消息内容。</p>
<p><button id="refresh" type="button">立即刷新</button> <span id="status" role="status" class="muted">正在读取…</span></p>
<div class="grid">
<section class="card"><h2>HTTP 请求</h2><div id="http-total" class="metric">—</div><div id="http-detail" class="muted">—</div></section>
<section class="card"><h2>API 进程</h2><div id="process-rss" class="metric">—</div><div id="process-detail" class="muted">—</div></section>
<section class="card"><h2>数据库连接池</h2><div id="pool-out" class="metric">—</div><div id="pool-detail" class="muted">—</div></section>
<section class="card"><h2>模型调用（近 15 分钟）</h2><div id="model-total" class="metric">—</div><div id="model-detail" class="muted">—</div></section>
<section class="card"><h2>任务事件流</h2><div id="event-total" class="metric">—</div><div id="event-detail" class="muted">—</div></section>
<section class="card"><h2>嵌入队列</h2><div id="embed-total" class="metric">—</div><div id="embed-detail" class="muted">—</div></section>
</div>
<section class="card"><h2>按路由</h2><table><thead><tr><th>方法 / 路由</th><th>次数 / 错误</th><th>平均 ms</th><th>峰值 ms</th></tr></thead><tbody id="routes"></tbody></table></section>
<section class="card"><h2>任务与状态</h2><table><thead><tr><th>类别</th><th>名称</th><th>数量</th></tr></thead><tbody id="jobs"></tbody></table></section>
<p class="muted">数据时间：<span id="generated">—</span> · 运行秒数：<span id="uptime">—</span></p>
<script src="/api/v2/local-monitor/assets.js"></script></html>"""

_SCRIPT = r"""
const byId = id => document.getElementById(id);
const text = (id, value) => { byId(id).textContent = String(value); };
function row(tbody, values) {
  const tr = document.createElement('tr');
  values.forEach(value => { const td = document.createElement('td'); td.textContent = String(value); tr.appendChild(td); });
  tbody.appendChild(tr);
}
async function refresh() {
  const button = byId('refresh'); button.disabled = true;
  try {
    const response = await fetch('/api/v2/local-monitor/data', {cache:'no-store', credentials:'same-origin'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const data = await response.json();
    text('http-total', data.http.total + ' 次');
    text('http-detail', '错误 ' + data.http.errors + ' · 近样本 P95 ' + data.http.p95Ms + ' ms · 峰值 ' + data.http.maxMs + ' ms');
    text('process-rss', data.process.available ? data.process.rssMiB + ' MiB' : '不可用');
    text('process-detail', data.process.available ? 'CPU ' + data.process.cpuPercent + '% · 线程 ' + data.process.threads + ' · PID ' + data.process.pid : '本环境未提供 psutil');
    const db = data.database;
    text('pool-out', db.pool.checkedOut + ' / ' + db.pool.size);
    text('pool-detail', (db.available ? '数据库可用' : '数据库不可用') + ' · 已归还 ' + db.pool.checkedIn + ' · 溢出 ' + db.pool.overflow);
    text('model-total', db.modelCalls.total + ' 次');
    text('model-detail', db.available ? '按现有 ModelCall 记录聚合 · 最老排队 ' + (db.oldestQueuedSeconds == null ? '—' : db.oldestQueuedSeconds + ' 秒') : '等待数据库恢复');
    text('event-total', data.events.subscribers + ' 个订阅');
    text('event-detail', (data.events.listenerActive ? '共享监听已连接' : '监听空闲') + ' · 涉及 ' + data.events.jobs + ' 个任务');
    const embed = data.embedding;
    text('embed-total', embed.available ? embed.queue.active + ' / ' + embed.queue.concurrency + ' 执行' : '不可用');
    text('embed-detail', embed.available ? '等待 ' + embed.queue.waiting + ' / ' + embed.queue.queueSize + ' · 状态 ' + embed.status : '回环嵌入服务未响应');
    const routes = byId('routes'); routes.replaceChildren();
    data.http.byRoute.forEach(item => row(routes, [item.method + ' ' + item.route, item.count + ' / ' + item.errors, item.avgMs, item.maxMs]));
    if (!data.http.byRoute.length) row(routes, ['暂无请求', '—', '—', '—']);
    const jobs = byId('jobs'); jobs.replaceChildren();
    Object.entries(db.jobs.byState).forEach(([name, count]) => row(jobs, ['状态', name, count]));
    Object.entries(db.jobs.byKind).forEach(([name, count]) => row(jobs, ['类型', name, count]));
    Object.entries(db.modelCalls.byStatus).forEach(([name, count]) => row(jobs, ['模型', name, count]));
    if (!jobs.children.length) row(jobs, ['暂无记录', '—', 0]);
    text('generated', data.generatedAt); text('uptime', data.uptimeSeconds);
    text('status', '更新成功'); byId('status').className = 'ok';
  } catch (error) { text('status', '读取失败：' + error.message); byId('status').className = 'bad'; }
  finally { button.disabled = false; }
}
byId('refresh').addEventListener('click', refresh);
setInterval(() => { if (!document.hidden) void refresh(); }, 5000);
void refresh();
"""


def require_local(request: Request) -> None:
    host = request.client.host if request.client else ""
    if not monitoring.enabled() or host not in {"127.0.0.1", "::1"}:
        raise ApiError("NOT_FOUND", "not found")


@router.get("/local-monitor", response_class=HTMLResponse, include_in_schema=False)
def page(request: Request):
    require_local(request)
    return HTMLResponse(_PAGE)


@router.get("/local-monitor/assets.js", include_in_schema=False)
def script(request: Request):
    require_local(request)
    return Response(_SCRIPT, media_type="text/javascript; charset=utf-8")


@router.get("/local-monitor/data", include_in_schema=False)
def data(request: Request):
    require_local(request)
    result = monitoring.snapshot()
    result["events"] = request.app.state.job_event_broker.snapshot()
    result["embedding"] = monitoring.embedding_snapshot()
    return result
