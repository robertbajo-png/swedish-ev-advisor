import assert from 'node:assert/strict';
import { revealFocusAboveCompareBar } from '../src/ui-navigation.js';

const saved = Object.fromEntries(['HTMLElement', 'document', 'window', 'requestAnimationFrame'].map(key => [key, globalThis[key]]));
try {
  let top = 820;
  const frames = [], scrolls = [];
  class Control {
    matches() { return true; }
    closest() { return null; }
    getBoundingClientRect() { return { top, bottom: top + 44 }; }
  }
  const target = new Control();
  const bar = { isConnected: true, contains: () => false, getBoundingClientRect: () => ({top: 814, bottom: 880}) };
  globalThis.HTMLElement = Control;
  globalThis.document = { activeElement: target, querySelector: () => bar };
  globalThis.window = { scrollBy(options) { scrolls.push(options); top -= options.top; } };
  globalThis.requestAnimationFrame = callback => frames.push(callback);
  const start = performance.now();
  revealFocusAboveCompareBar({target});
  assert(top + 44 < 814);
  frames.shift()(start + 16);
  // Reproduce the browser's delayed native focus scroll after our first frame.
  top = 820;
  assert(frames.length);
  frames.shift()(start + 64);
  assert(top + 44 < 814, 'Delayed native scrolling must not leave focus covered');
  while (frames.length) frames.shift()(start + 300);
  assert.equal(frames.length, 0, 'Focus correction is bounded, not a permanent loop');
  assert(scrolls.every(s => s.behavior === 'instant'));
  revealFocusAboveCompareBar({target});
  document.activeElement = null;
  frames.shift()(start + 100);
  assert.equal(frames.length, 0, 'Stop as soon as focus moves away');
  document.activeElement = target;
  revealFocusAboveCompareBar({target});
  bar.isConnected = false;
  frames.shift()(start + 100);
  assert.equal(frames.length, 0, 'Stop when the comparison overlay is removed');
  console.log(JSON.stringify({delayed_native_focus_scroll:'passed',bounded_recheck:true,reduced_motion_preserved:true}));
} finally {
  for (const [key,value] of Object.entries(saved)) {
    if (value === undefined) delete globalThis[key];
    else globalThis[key] = value;
  }
}
