(() => {
  const starts = new Map();
  let frame = 0;
  const visible = node => node && node.getClientRects().length && !node.closest('.hide,[hidden]');
  function sizeGoal() {
    if (window.CSS?.supports('field-sizing', 'content')) return;
    const input = document.querySelector('#le-onboarding-topic textarea');
    if (!visible(input)) return;
    const style = getComputedStyle(input);
    const border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    input.style.setProperty('--le-goal-height', '1px');
    input.style.setProperty('--le-goal-height', `${Math.ceil(input.scrollHeight + border)}px`);
  }
  function updateViewport() {
    frame = 0;
    sizeGoal();
    const row = document.getElementById('le-workbench-row');
    if (!visible(row)) return;
    const height = Math.max(240, Math.floor(innerHeight - row.getBoundingClientRect().top - 16));
    const value = `${height}px`;
    if (row.style.getPropertyValue('--le-workbench-height') !== value) row.style.setProperty('--le-workbench-height', value);
  }
  function schedule() {
    if (!frame) frame = requestAnimationFrame(updateViewport);
  }
  function tick() {
    const active = new Set();
    document.querySelectorAll('[data-le-wait-id]').forEach(panel => {
      const id = panel.dataset.leWaitId;
      active.add(id);
      if (!starts.has(id)) starts.set(id, Date.now());
      const label = panel.querySelector('[data-le-elapsed]');
      if (!label || !visible(panel)) return;
      const elapsed = Math.max(0, Math.floor((Date.now() - starts.get(id)) / 1000));
      const time = elapsed < 60 ? `${elapsed} 秒` : `${Math.floor(elapsed / 60)} 分 ${elapsed % 60} 秒`;
      const text = `已等待 ${time} · 耗时取决于模型和网络`;
      if (label.textContent !== text) label.textContent = text;
    });
    for (const id of starts.keys()) if (!active.has(id)) starts.delete(id);
  }
  document.addEventListener('error', event => {
    const img = event.target;
    if (img.tagName !== 'IMG' || !img.closest('#le-app-tabs,.le-brand') || img.dataset.leImageFailed) return;
    img.dataset.leImageFailed = 'true';
    const message = document.createElement('span');
    message.className = 'le-image-fallback';
    message.textContent = img.alt || '图片暂时无法显示';
    message.setAttribute('role', 'img');
    message.setAttribute('aria-label', message.textContent);
    img.hidden = true;
    img.after(message);
    img.addEventListener('load', () => {
      img.hidden = false;
      delete img.dataset.leImageFailed;
      message.remove();
    }, {once:true});
  }, true);
  function start() {
    document.addEventListener('click', event => {
      const tab = event.target.closest?.('#learning-review-tab-button, #learning-quiz-tab-button');
      if (!tab) return;
      const refresh = tab.id === 'learning-review-tab-button' ? 'le-review-refresh' : 'le-quiz-goal-refresh';
      document.getElementById(refresh)?.click();
    });
    new MutationObserver(schedule).observe(document.body, {childList:true,subtree:true,attributes:true,attributeFilter:['class','hidden']});
    window.addEventListener('resize', schedule, {passive:true});
    window.visualViewport?.addEventListener('resize', schedule, {passive:true});
    document.addEventListener('input', event => {
      if (event.target.matches?.('#le-onboarding-topic textarea')) schedule();
    });
    document.fonts?.ready.then(schedule);
    if (window.ResizeObserver) {
      const observer = new ResizeObserver(schedule);
      const strip = document.getElementById('le-left-col');
      if (strip) observer.observe(strip);
    }
    schedule(); tick(); setInterval(tick, 1000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
