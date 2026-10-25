import { json } from './_shared/http.mjs';
import { checkReadiness } from './_shared/readiness.mjs';

export async function onRequestGet(context) {
  if (context?.request && new URL(context.request.url).searchParams.get('readiness') === '1') {
    const result = await checkReadiness(context);
    return json({ service: 'seekev-api', ...result }, result.ok ? 200 : 503);
  }
  return json({ ok: true, service: 'seekev-api' });
}

export function onRequest() {
  return json({ error: 'Method not allowed.' }, 405);
}
