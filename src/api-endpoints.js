export function advisorEndpoints(path, { basePath = '/', hostname = '', development = false } = {}) {
  const sameOrigin = `${basePath.replace(/\/$/, '')}${path}`;
  const localHost = ['localhost', '127.0.0.1', '[::1]'].includes(hostname);
  return development && localHost
    ? [sameOrigin, `http://127.0.0.1:8787${path}`]
    : [sameOrigin];
}
