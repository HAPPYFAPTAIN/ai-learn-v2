(() => {
  let scheduled = false;
  const positioned = new WeakSet();
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const options = event.target.closest?.('.wrap')?.querySelector('ul.options[role="listbox"]');
    if (options?.getClientRects().length) event.preventDefault();
  }, true);
  function positionBelow(menu, input) {
    if (!menu.closest('#quick-setup-tab') || !input || input.getAttribute('aria-expanded') !== 'true') return;
    const anchor = input.closest('.wrap');
    if (!anchor) return;
    const viewport = window.visualViewport;
    const edge = 12, gap = 6;
    const viewportTop = viewport?.offsetTop || 0;
    const viewportLeft = viewport?.offsetLeft || 0;
    const width = viewport?.width || document.documentElement.clientWidth || innerWidth;
    const height = viewport?.height || innerHeight;
    const bottom = viewportTop + height;
    let rect = anchor.getBoundingClientRect();
    if (!positioned.has(menu)) {
      positioned.add(menu);
      if (bottom - rect.bottom - gap - edge < Math.min(160, height / 3)) {
        input.scrollIntoView({block:'center', inline:'nearest', behavior:'instant'});
        rect = anchor.getBoundingClientRect();
      }
    }
    const menuWidth = Math.max(0, Math.min(rect.width, width - edge * 2));
    const top = Math.max(viewportTop + edge, rect.bottom + gap);
    const left = Math.max(viewportLeft + edge, Math.min(rect.left, viewportLeft + width - menuWidth - edge));
    const room = Math.max(0, Math.min(320, bottom - top - edge));
    const properties = {'--le-select-top': top, '--le-select-left': left, '--le-select-width': menuWidth, '--le-select-height': room};
    for (const [name, value] of Object.entries(properties)) {
      const css = `${Math.round(value)}px`;
      if (menu.style.getPropertyValue(name) !== css) menu.style.setProperty(name, css);
    }
    if (menu.dataset.lePlacement !== 'below') menu.dataset.lePlacement = 'below';
  }
  function decorate() {
    scheduled = false;
    document.querySelectorAll('ul.options[role="listbox"]').forEach(menu => {
      const input = menu.parentElement.querySelector('input[role="listbox"]');
      positionBelow(menu, input);
      const room = menu.style.maxHeight || '48dvh';
      if (menu.style.getPropertyValue('--le-menu-room') !== room) menu.style.setProperty('--le-menu-room', room);
      const hint = input && !input.readOnly && !input.disabled ? '输入关键词筛选 · ↑↓ 选择 / Enter 确认' : '↑↓ 选择 · Enter 确认';
      if (menu.dataset.leHint !== hint) menu.dataset.leHint = hint;
      menu.querySelectorAll('[role="option"]').forEach(option => {
        const label = option.getAttribute('aria-label');
        if (label && option.title !== label) option.title = label;
      });
    });
  }
  function schedule() {
    if (!scheduled) { scheduled = true; requestAnimationFrame(decorate); }
  }
  function start() {
    new MutationObserver(mutations => {
      if (mutations.some(mutation => {
        const target = mutation.target.nodeType === 1 ? mutation.target : mutation.target.parentElement;
        return !target?.closest('#le-coach-transcript,#le-coach-stream');
      })) schedule();
    }).observe(document.body, {childList:true, subtree:true, attributes:true, attributeFilter:['style','aria-expanded','aria-label']});
    window.addEventListener('resize', schedule, {passive:true});
    window.addEventListener('scroll', event => {
      if (!event.target.closest?.('ul.options[role="listbox"]')) schedule();
    }, {passive:true, capture:true});
    window.visualViewport?.addEventListener('resize', schedule, {passive:true});
    window.visualViewport?.addEventListener('scroll', schedule, {passive:true});
    schedule();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
