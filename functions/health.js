import { json } from './_shared/http.mjs';

export function onRequestGet() {
  return json({ ok: true, service: 'seekev-api' });
}

export function onRequest() {
  return json({ error: 'Method not allowed.' }, 405);
}
