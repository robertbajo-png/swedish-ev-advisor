export function preferredScrollBehavior() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
}

export function revealFocusAboveCompareBar(event) {
  const target = event.target;
  const bar = document.querySelector('.vehicleCompareBar');
  if (!bar || !(target instanceof HTMLElement) || bar.contains(target) || target.closest('dialog[open]') || !target.matches('a, button, input, select, textarea, summary')) return;
  const reveal = () => {
    const control = target.getBoundingClientRect();
    const overlay = bar.getBoundingClientRect();
    if (control.bottom > overlay.top - 12 && control.top < overlay.bottom) {
      window.scrollBy({ top: Math.ceil(control.bottom - overlay.top + 16), behavior: 'instant' });
    }
  };
  reveal();
  // Recheck after native focus scrolling and newly reserved footer space settle.
  requestAnimationFrame(() => {
    if (document.activeElement === target && bar.isConnected) reveal();
  });
}
