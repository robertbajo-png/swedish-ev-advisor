
const basePath = (import.meta.env.VITE_APP_BASE_PATH || '').replace(/\/$/, '');

export const isPreview = import.meta.env.VITE_BILJOURNAL_PREVIEW === '1';
export const isOfflineReview = () => typeof window !== 'undefined' && window.location.protocol === 'file:';

export function sitePath(path) {
  if (isOfflineReview()) return '#' + path;
  return basePath + path;
}

export function assetPath(path) {
  if (!path?.startsWith('/')) return path;
  if (isOfflineReview()) return window.__BILJOURNAL_ASSETS__?.[path] || '';
  return basePath + path;
}
