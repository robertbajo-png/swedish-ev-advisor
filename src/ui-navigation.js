export function preferredScrollBehavior() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
}

export function revealFocusAboveCompareBar(event) {
  const target = event.target;
  const bar = document.querySelector('.vehicleCompareBar');
  if (!bar || !(target instanceof HTMLElement) || bar.contains(target) || target.closest('dialog[open]') || !target.matches('a, button, input, select, textarea, summary')) return;
  const control = target.getBoundingClientRect();
  const overlay = bar.getBoundingClientRect();
  // Native focus scrolling does not account for a fixed overlay.
  if (control.bottom > overlay.top - 12 && control.top < overlay.bottom) {
    window.scrollBy({ top: Math.ceil(control.bottom - overlay.top + 16), behavior: 'instant' });
  }
}
