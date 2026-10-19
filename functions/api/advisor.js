import { createAdvisorResult } from '../_shared/advisor-core.mjs';
import { json, loadPublicVariants, readJsonRequest, runtimeOptions } from '../_shared/http.mjs';
import { guardAiRequest } from '../_shared/ai-guard.mjs';

export async function onRequestPost(context) {
  const guard = guardAiRequest(context.request, context.env);
  if (guard.response) return guard.response;
  try {
    const request = await readJsonRequest(context.request);
    const variants = await loadPublicVariants(context);
    const result = await createAdvisorResult({ request, variants, ...runtimeOptions(context.env, context.request) });
    return json(result);
  } catch (error) {
    const status = error instanceof SyntaxError || /too large/i.test(error.message) ? 400 : 503;
    console.error('Advisor request failed with HTTP status', status);
    return json({ error: status === 400 ? 'Ogiltig förfrågan.' : 'Rådgivaren är tillfälligt otillgänglig.' }, status);
  } finally { guard.release(); }
}

export function onRequest() {
  return json({ error: 'Method not allowed.' }, 405);
}
