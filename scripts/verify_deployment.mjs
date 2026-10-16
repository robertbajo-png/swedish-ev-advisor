import { pathToFileURL } from 'node:url';

const isLocal = (url) => /^(localhost|127\.[\d.]+|0\.0\.0\.0|\[::1\])$/i.test(url.hostname);

export async function verifyDeployment(baseUrl, { fetchImpl = fetch, expectPreview = false } = {}) {
  const base = new URL(baseUrl);
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash) throw new Error('Use an HTTP(S) site URL without credentials, query or fragment.');
  base.pathname = base.pathname.replace(/\/$/, '') + '/';
  const report = { origin: base.origin, checks: [], publicVariants: null, apiPostsMade: false, ok: false };
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
      if (!/text\/html/i.test(headers.get('content-type') || '') || !/id=["']root["']/.test(body) || !body.includes('Elbilsguiden')) throw new Error('Expected the Elbilsguiden application, not a parking/error page.');
      if (expectPreview && !/noindex/i.test(headers.get('x-robots-tag') || '')) throw new Error('Preview is missing the noindex response header.');
      return {};
    });
  }
  await check('health', (body, headers) => {
    const payload = asJson(body, headers);
    if (payload.ok !== true || payload.service !== 'seekev-api') throw new Error('SeekEV API health contract failed.');
    return { service: payload.service };
  });
  await check('data/public_ev_variants.json', (body, headers) => {
    const records = asJson(body, headers).records;
    if (!Array.isArray(records) || !records.length) throw new Error('Published canonical snapshot is empty or invalid.');
    const keys = records.map((row) => [row.brand, row.model, row.variant_name].join('|'));
    if (new Set(keys).size !== records.length) throw new Error('Duplicate canonical variants in snapshot.');
    if (records.some((row) => !['published', 'published_reviewed'].includes(row.validation_status) || !row.source_hash || !/^https:\/\//.test(row.source_url || '') || !row.brand || !row.model)) throw new Error('Snapshot contains unpublished or unsourced variants.');
    report.publicVariants = records.length;
    return { records: records.length };
  });
  await check('sitemap.xml', (body, headers) => {
    if (!/(?:application|text)\/xml/i.test(headers.get('content-type') || '') || !/<urlset[\s>]/.test(body) || !/<loc>[^<]+\/bilar\//.test(body)) throw new Error('Expected an XML sitemap containing car detail URLs.');
    return {};
  });
  report.ok = report.checks.every((item) => item.ok);
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const target = process.argv.slice(2).find((value) => !value.startsWith('--'));
  if (!target) {
    console.error('Usage: node scripts/verify_deployment.mjs <site-url> [--expect-preview]');
    process.exitCode = 2;
  } else {
    try {
      const report = await verifyDeployment(target, { expectPreview: process.argv.includes('--expect-preview') });
      console.log(JSON.stringify(report, null, 2));
      process.exitCode = report.ok ? 0 : 1;
    } catch (error) { console.error(error.message); process.exitCode = 2; }
  }
}
