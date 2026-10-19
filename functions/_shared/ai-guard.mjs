import { json } from './http.mjs';

// Best-effort beta protection per isolate, not a distributed spending limit.
export function createAiGuard({ now = Date.now, limit = 5, windowMs = 60000, maxConcurrent = 2, maxClients = 5000 } = {}) {
  const clients = new Map();
  let active = 0;
  return (request, env) => {
    if (!env.OPENAI_API_KEY) return { release() {} };
    const origin = request.headers.get('origin');
    if (origin && origin !== new URL(request.url).origin) return { response: json({ error: 'Otillåtet ursprung.' }, 403) };
    if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get('content-type') || '')) return { response: json({ error: 'JSON krävs.' }, 415) };
    const time = now();
    for (const [key, client] of clients) if (client.expires <= time) clients.delete(key);
    const key = request.headers.get('cf-connecting-ip') || 'unknown';
    const client = clients.get(key) || { count: 0, expires: time + windowMs };
    if (client.count >= limit || active >= maxConcurrent || (!clients.has(key) && clients.size >= maxClients)) {
      const retryAfter = client.count >= limit ? Math.ceil((client.expires - time) / 1000) : 5;
      return { response: json({ error: 'För många förfrågningar. Försök igen om en stund.' }, 429, { 'retry-after': String(retryAfter) }) };
    }
    client.count++;
    clients.set(key, client);
    active++;
    let released = false;
    return {
      release() {
        if (!released) { active--; released = true; }
      },
    };
  };
}

export const guardAiRequest = createAiGuard();
