MARKUP='''<section id="le-storage-root" aria-labelledby="le-storage-title">
<header><div><h1 id="le-storage-title">空间管理</h1><p>你的个人学习空间 · 初始 5 GB</p></div><button type="button" data-storage-refresh>刷新用量</button></header>
<p data-storage-status role="status" aria-live="polite">正在读取个人空间…</p>
<section class="le-storage-usage" aria-label="存储用量"><div class="le-storage-total"><strong data-storage-used>—</strong><span> / 5 GB</span><small data-storage-remaining></small></div>
<div class="le-storage-meter" role="progressbar" aria-label="已用空间" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><span></span></div>
<h2>已用空间构成</h2><div class="le-storage-parts" aria-hidden="true"></div><ul data-storage-categories></ul></section>
<section class="le-storage-files"><header><div><h2>我的文件与记录</h2><p>资料、课程、问答、附件和个人文件均属于当前账号。</p></div><button type="button" data-storage-batch>批量下载</button></header>
<div class="le-storage-toolbar"><label><span class="le-sr-only">查找文件与记录</span><input type="search" placeholder="搜索名称…" aria-label="查找文件与记录"></label>
<label><span class="le-sr-only">显示类型</span><select aria-label="显示类型"><option value="all">全部类型</option><option value="source">资料文件</option><option value="project">课程与学习记录</option><option value="conversation">问答记录</option><option value="file">个人文件与附件</option></select></label>
<span data-storage-selection hidden><button type="button" data-storage-none>全部不选</button><button type="button" data-storage-all>全选</button><button type="button" data-storage-download-selected>下载所选</button></span></div>
<div data-storage-list></div><p data-storage-empty hidden>当前没有匹配的文件或记录。</p>
<nav class="le-storage-pagination" aria-label="文件分页"><span data-storage-page></span><button type="button" data-storage-prev>上一页</button><button type="button" data-storage-next>下一页</button></nav>
<p class="le-storage-note">学习记录与检索索引也计入用量。删除需确认；正在生成内容或备课时，先等待任务完成。</p></section>
<dialog id="le-storage-confirm" aria-labelledby="le-storage-confirm-title"><h2 id="le-storage-confirm-title">永久删除这项内容？</h2><p data-storage-delete-name></p><p>删除后无法恢复。课程会一并删除对应笔记、卡片和测验记录。</p><div><button type="button" data-storage-cancel>取消</button><button type="button" data-storage-confirm-delete>确认删除</button></div></dialog>
</section>'''
