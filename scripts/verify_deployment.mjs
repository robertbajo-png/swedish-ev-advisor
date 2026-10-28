import { pathToFileURL } from 'node:url';
import { readFile } from 'node:fs/promises';
import { parse } from 'parse5';
import { SITE_ORIGIN } from '../src/site-info.js';
import { catalogHash } from './sync_public_catalog.mjs';

const isLocal = (url) => /^(localhost|127\.[\d.]+|0\.0\.0\.0|\[::1\])$/i.test(url.hostname);

function productionMetadata(body, headers, canonical) {
  const nodes = [parse(body)], links = [];
  if (/\b(?:noindex|none)\b/i.test(headers.get('x-robots-tag') || '')) throw new Error('Production is marked noindex.');
  while (nodes.length) {
    const node = nodes.pop(), attrs = Object.fromEntries((node.attrs || []).map(({name,value}) => [name,value]));
    if (node.tagName === 'meta' && /^(robots|googlebot|bingbot)$/i.test(attrs.name || '')
        && /\b(?:noindex|none)\b/i.test(attrs.content || '')) throw new Error('Production HTML is marked noindex.');
    if (node.tagName === 'link' && (attrs.rel || '').toLowerCase().split(/\s+/).includes('canonical')) links.push(attrs.href);
    nodes.push(...(node.childNodes || []));
  }
  if (links.length !== 1 || links[0] !== canonical) throw new Error('Production canonical URL does not match this route.');
  if (headers.get('x-content-type-options') !== 'nosniff') throw new Error('Production is missing nosniff protection.');
}

export async function verifyDeployment(baseUrl, { fetchImpl = fetch, expectPreview = false, expectProduction = false, expectedCatalogHash, expectedSitemap } = {}) {
  const base = new URL(baseUrl);
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash) throw new Error('Use an HTTP(S) site URL without credentials, query or fragment.');
  if (base.origin === SITE_ORIGIN && !expectProduction) throw new Error('The public production origin requires --production verification.');
  if (expectProduction && (expectPreview || base.origin !== SITE_ORIGIN || base.pathname !== '/'
      || !/^[a-f0-9]{64}$/.test(expectedCatalogHash || '') || !expectedSitemap?.trim())) throw new Error('Production requires the exact HTTPS origin, root path and approved catalog/sitemap.');
  base.pathname = base.pathname.replace(/\/$/, '') + '/';
  const report = { origin: base.origin, checks: [], publicVariants: null, apiPostsMade: false, productionChecked: expectProduction, providerTested: false, ok: false };
  const check = async (path, validate) => {
    try {
      let url = new URL(path, base);
      let response;
      for (let redirects = 0; redirects <= 4; redirects++) {
        response = await fetchImpl(url.href, { redirect: 'manual', signal: AbortSignal.timeout(15000) });
        if (![301, 302, 303, 307, 308].includes(response.status)) break;
        const location = response.headers.get('location');
        if (!location) throw new Error('Redirect has no destination.');
        url = new URL(location, url);
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('Unsafe redirect destination.');
        if (!isLocal(base) && isLocal(url)) throw new Error('Public site redirects to localhost.');
        if (base.protocol === 'https:' && url.protocol !== 'https:') throw new Error('HTTPS redirects to an insecure URL.');
        if (expectProduction && url.origin !== base.origin) throw new Error('Production redirects away from its own origin.');
      }
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const body = await response.text();
      const detail = validate(body, response.headers);
      report.checks.push({ path, ok: true, ...detail });
    } catch (error) {
      report.checks.push({ path, ok: false, error: error.cause?.code || error.message });
    }
  };
  const asJson = (body, headers) => {
    if (!/application\/(?:[\w.-]+\+)?json/i.test(headers.get('content-type') || '')) throw new Error('Expected JSON, not an HTML fallback or parking page.');
    return JSON.parse(body);
  };
  for (const path of ['', 'bilar', 'jamfor', 'nyheter', 'bilar/tesla-model-3-long-range-rwd/']) {
    await check(path, (body, headers) => {
      if (!/text\/html/i.test(headers.get('content-type') || '') || !/id=["']root["']/.test(body) || !body.includes('Elbilsagenten')) throw new Error('Expected the Elbilsagenten application, not a parking/error page.');
      if (expectPreview && !/noindex/i.test(headers.get('x-robots-tag') || '')) throw new Error('Preview is missing the noindex response header.');
      if (expectProduction) productionMetadata(body, headers, new URL(path.replace(/\/$/, '') || '/', base).href);
      return {};
    });
  }
  await check('health', (body, headers) => {
    const payload = asJson(body, headers);
    if (payload.ok !== true || payload.service !== 'seekev-api') throw new Error('SeekEV API health contract failed.');
    return { service: payload.service };
  });
  await check('data/public_ev_variants.json', (body, headers) => {
    const snapshot = asJson(body, headers), records = snapshot.records;
    if (!Array.isArray(records) || !records.length) throw new Error('Published canonical snapshot is empty or invalid.');
    const keys = records.map((row) => [row.brand, row.model, row.variant_name].join('|'));
    if (new Set(keys).size !== records.length) throw new Error('Duplicate canonical variants in snapshot.');
    if (records.some((row) => !['published', 'published_reviewed'].includes(row.validation_status) || !row.source_hash || !/^https:\/\//.test(row.source_url || '') || !row.brand || !row.model)) throw new Error('Snapshot contains unpublished or unsourced variants.');
    if (expectProduction && (snapshot.source !== 'supabase_public_ev_variants' || snapshot.catalog_sha256 !== expectedCatalogHash
        || catalogHash(records) !== expectedCatalogHash)) throw new Error('Deployed canonical catalog differs from the approved snapshot.');
    report.publicVariants = records.length;
    return { records: records.length };
  });
  await check('sitemap.xml', (body, headers) => {
    if (!/(?:application|text)\/xml/i.test(headers.get('content-type') || '') || !/<urlset[\s>]/.test(body) || !/<loc>[^<]+\/bilar\//.test(body)) throw new Error('Expected an XML sitemap containing car detail URLs.');
    if (expectProduction && body.replaceAll('\r\n','\n').trim() !== expectedSitemap.replaceAll('\r\n','\n').trim()) throw new Error('Production sitemap differs from the approved artifact.');
    return {};
  });
  if (expectProduction) {
    await check('health?readiness=1', (body, headers) => {
      const result = asJson(body, headers);
      if (result.ok !== true || result.service !== 'seekev-api' || result.ai_enabled !== true || result.provider_tested !== false
          || result.paid_calls !== 0 || !['catalog','ai_configuration','budget_storage'].every(name => result.checks?.[name] === true)) {
        throw new Error('Production catalog, AI configuration or durable budget is not ready.');
      }
      return { configured: true, providerTested: false, paidCalls: 0 };
    });
    await check('robots.txt', body => {
      const approved = `User-agent: *\nAllow: /\nSitemap: ${SITE_ORIGIN}/sitemap.xml`;
      if (body.replaceAll('\r\n','\n').trim() !== approved) throw new Error('robots.txt differs from the approved indexable production policy.');
      return { approvedPolicy: true };
    });
  }
  report.ok = report.checks.every((item) => item.ok);
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const target = process.argv.slice(2).find((value) => !value.startsWith('--'));
  if (!target) {
    console.error('Usage: node scripts/verify_deployment.mjs <site-url> [--expect-preview | --production]');
    process.exitCode = 2;
  } else {
    try {
      const production = process.argv.includes('--production');
      const snapshot = production ? JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json', import.meta.url), 'utf8')) : null;
      const sitemap = production ? await readFile(new URL('../public/sitemap.xml', import.meta.url), 'utf8') : null;
      const report = await verifyDeployment(target, { expectPreview: process.argv.includes('--expect-preview'),
        expectProduction: production, expectedCatalogHash: snapshot?.catalog_sha256, expectedSitemap: sitemap });
      console.log(JSON.stringify(report, null, 2));
      process.exitCode = report.ok ? 0 : 1;
    } catch (error) { console.error(error.message); process.exitCode = 2; }
  }
}
