import { createCompareResult } from '../_shared/advisor-core.mjs';
import { json, loadPublicVariants, readJsonRequest, runtimeOptions } from '../_shared/http.mjs';

export async function onRequestPost(context) {
  try {
    const request = await readJsonRequest(context.request);
    const variants = await loadPublicVariants(context);
    const result = await createCompareResult({
      variantKeys: request.variant_keys,
      variants,
      ...runtimeOptions(context.env),
    });
    if (!result) return json({ error: 'Inga valda publicerade bilar kunde matchas.' }, 400);
    return json(result);
  } catch (error) {
    const status = error instanceof SyntaxError || /too large/i.test(error.message) ? 400 : 503;
    console.error('Compare request failed:', error.message);
    return json({ error: status === 400 ? 'Ogiltig förfrågan.' : 'Jämförelserapporten är tillfälligt otillgänglig.' }, status);
  }
}

export function onRequest() {
  return json({ error: 'Method not allowed.' }, 405);
}
