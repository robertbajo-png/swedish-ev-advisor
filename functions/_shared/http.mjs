import { normalizePublicVariants } from './advisor-core.mjs';

const RESPONSE_HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'cache-control': 'no-store',
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'strict-origin-when-cross-origin',
};

let cachedVariants = null;
let cacheExpiresAt = 0;

export function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: RESPONSE_HEADERS });
}

export async function readJsonRequest(request) {
  const contentLength = Number(request.headers.get('content-length') || 0);
  if (contentLength > 20000) throw new Error('Request body is too large.');
  const body = await request.text();
  if (!body) return {};
  if (body.length > 20000) throw new Error('Request body is too large.');
  return JSON.parse(body);
}

async function loadFromSupabase(env) {
  const baseUrl = env.SUPABASE_URL || env.VITE_SUPABASE_URL;
  const anonKey = env.SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY;
  if (!baseUrl || !anonKey) return [];
  const response = await fetch(`${baseUrl.replace(/\/$/, '')}/rest/v1/public_ev_variants?select=*`, {
    headers: { apikey: anonKey, authorization: `Bearer ${anonKey}` },
  });
  if (!response.ok) throw new Error(`Supabase public view returned ${response.status}.`);
  return normalizePublicVariants(await response.json());
}

async function loadFromStaticExport(context) {
  if (!context.env.ASSETS?.fetch) return [];
  const url = new URL('/data/public_ev_variants.json', context.request.url);
  const response = await context.env.ASSETS.fetch(new Request(url));
  if (!response.ok) throw new Error(`Static public export returned ${response.status}.`);
  const payload = await response.json();
  return normalizePublicVariants(Array.isArray(payload) ? payload : payload.records);
}

export async function loadPublicVariants(context) {
  if (cachedVariants && Date.now() < cacheExpiresAt) return cachedVariants;
  const errors = [];
  let variants = [];
  try {
    variants = await loadFromSupabase(context.env);
  } catch (error) {
    errors.push(error.message);
  }
  if (!variants.length) {
    try {
      variants = await loadFromStaticExport(context);
    } catch (error) {
      errors.push(error.message);
    }
  }
  if (!variants.length) throw new Error(errors.join(' ') || 'No published canonical variants available.');
  cachedVariants = variants;
  cacheExpiresAt = Date.now() + 5 * 60 * 1000;
  return variants;
}

export function runtimeOptions(env) {
  return {
    apiKey: env.OPENAI_API_KEY || '',
    model: env.OPENAI_MODEL || 'gpt-5.4-mini',
  };
}
