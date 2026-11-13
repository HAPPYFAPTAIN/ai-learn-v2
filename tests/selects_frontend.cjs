const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const frames = [];
const documentEvents = new Map();
const windowEvents = new Map();
let height = 1000;
let width = 1200;
function dropdown(settings = true) {
  const values = new Map();
  const field = {
    rect: {left: 300, top: 100, bottom: 144, width: 600},
    getBoundingClientRect() { return this.rect; },
    querySelector() { return menu; },
  };
  const input = {
    value: 'deepseek-chat', readOnly: false, disabled: false, scrolls: 0, expanded: 'true',
    getAttribute(name) { return name === 'aria-expanded' ? this.expanded : null; },
    closest() { return field; },
    scrollIntoView(options) {
      assert.equal(options.block, 'center');
      this.scrolls += 1;
      field.rect = {...field.rect, top: 450, bottom: 494};
    },
  };
  const option = {
    title: '', selected: true,
    getAttribute(name) { return name === 'aria-label' ? 'deepseek-chat' : null; },
  };
  const menu = {
    dataset: {}, writes: 0,
    style: {
      maxHeight: 'calc(700px - 32px)',
      getPropertyValue(name) { return values.get(name) || ''; },
      setProperty(name, value) { menu.writes += 1; values.set(name, value); },
    },
    parentElement: {querySelector() { return input; }},
    closest() { return settings ? {} : null; },
    getClientRects() { return [field.rect]; },
    querySelectorAll() { return [option]; },
  };
  return {field, input, menu, option, value: name => values.get(`--le-select-${name}`)};
}
const config = dropdown();
const chat = dropdown(false);
const document = {
  readyState: 'complete', body: {}, documentElement: {get clientWidth() { return width; }},
  querySelectorAll() { return [config.menu, chat.menu]; },
  addEventListener(name, callback) { documentEvents.set(name, callback); },
};
const window = {
  visualViewport: null,
  addEventListener(name, callback) { windowEvents.set(name, callback); },
};
const context = {
  document, window,
  get innerHeight() { return height; },
  get innerWidth() { return width; },
  WeakSet,
  requestAnimationFrame(callback) { frames.push(callback); },
  MutationObserver: class { observe() {} },
};
vm.runInNewContext(fs.readFileSync('learning_ext/assets/selects.js', 'utf8'), context);
function flush() {
  assert(frames.length < 3, 'Repositioning must batch into one animation frame');
  while (frames.length) frames.shift()();
}
function resize() { windowEvents.get('resize')(); flush(); }
flush();
assert.equal(config.menu.dataset.lePlacement, 'below');
assert.equal(config.value('top'), '150px');
assert.equal(config.value('width'), '600px');
assert.equal(config.value('height'), '320px');
assert.equal(chat.menu.dataset.lePlacement, undefined, 'Chat menus retain their own positioning');
assert.equal(config.option.title, 'deepseek-chat');

config.field.rect = {...config.field.rect, top: 500, bottom: 544};
resize();
assert.equal(config.value('top'), '550px', 'A field in the lower half still opens downward');
assert.equal(config.input.scrolls, 0);
config.field.rect = {...config.field.rect, top: 700, bottom: 744};
resize();
assert.equal(config.value('height'), '238px', 'The menu scrolls within available space');

const writes = config.menu.writes;
resize();
assert.equal(config.menu.writes, writes, 'Unchanged measurements must not trigger a style mutation loop');
config.input.expanded = 'false';
config.field.rect = {...config.field.rect, top: 900, bottom: 944};
resize();
assert.equal(config.value('top'), '750px', 'Closing menus do not move');

const nearBottom = dropdown();
nearBottom.field.rect = {...nearBottom.field.rect, top: 900, bottom: 944};
document.querySelectorAll = () => [nearBottom.menu];
resize();
assert.equal(nearBottom.input.scrolls, 1, 'A newly opened field near the bottom scrolls into view once');
assert.equal(nearBottom.value('top'), '500px');
height = 650;
resize();
assert.equal(nearBottom.value('top'), '500px');
assert.equal(nearBottom.value('height'), '138px');
assert.equal(nearBottom.input.scrolls, 1, 'Resize does not repeatedly recenter a field');
nearBottom.field.rect = {left: -8, top: 110, bottom: 154, width: 800};
width = 320;
windowEvents.get('scroll')({target: {closest() { return null; }}});
flush();
assert.equal(nearBottom.value('top'), '160px');
assert.equal(nearBottom.value('left'), '12px');
assert.equal(nearBottom.value('width'), '296px');
windowEvents.get('scroll')({target: {closest() { return nearBottom.menu; }}});
assert.equal(frames.length, 0, 'Scrolling the options must not reposition the popup');

window.visualViewport = {offsetTop: 10, offsetLeft: 20, width: 280, height: 400};
resize();
assert.equal(nearBottom.value('left'), '32px');
assert.equal(nearBottom.value('width'), '256px');
assert.equal(nearBottom.value('height'), '238px');

for (const key of ['ArrowDown', 'Enter', 'Escape']) {
  const event = {key, target: nearBottom.input, prevented: false, preventDefault() { this.prevented = true; }};
  documentEvents.get('keydown')(event);
  assert.equal(event.prevented, key === 'Escape', 'Preserve native arrow/Enter selection and Escape handling');
}
assert.equal(nearBottom.input.value, 'deepseek-chat');
assert.equal(nearBottom.option.selected, true);
console.log('Dropdown positioning, resize, scrolling, viewport and keyboard checks passed');
