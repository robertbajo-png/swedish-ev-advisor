import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createServer } from 'vite';
import { parse } from 'parse5';
import { isPublishedArticle, publicArticles } from '../src/news-presentation.js';
import { PUBLIC_CONTENT_VERSION } from '../src/public-content-version.js';

export function safePageData(value) {
  return JSON.stringify(value).replace(/[<>&\u2028\u2029]/g, (char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, '0')}`);
}

function descendants(root) {
  const nodes = [], queue = [root];
  while (queue.length) { const node = queue.shift(); nodes.push(node); queue.unshift(...(node.childNodes || [])); }
  return nodes;
}

export function synchronizeItemList(html, content, origin) {
  const attr = (node, name) => node.attrs?.find((item) => item.name === name)?.value;
  const scripts = descendants(parse(html, { sourceCodeLocationInfo: true })).filter((node) => node.tagName === 'script' && attr(node, 'data-prerender') === 'page');
  const target = scripts.map((script) => {
    const payload = JSON.parse(script.childNodes.map((node) => node.value || '').join(''));
    return { script, payload, list: (Array.isArray(payload) ? payload : [payload]).find((node) => node['@type'] === 'ItemList') };
  }).find((item) => item.list);
  if (!target) return html;
  const text = (node) => descendants(node).filter((item) => item.nodeName === '#text').map((item) => item.value).join('').trim();
  const cards = descendants(parse(content)).filter((node) => node.tagName === 'article' && (attr(node, 'class') || '').split(' ').includes('vehicleCard'));
  const items = cards.map((card, index) => {
    const nodes = descendants(card);
    const link = nodes.find((node) => node.tagName === 'a' && attr(node, 'href')?.includes('/bilar/'));
    const heading = nodes.find((node) => node.tagName === 'h2');
    const variant = nodes.find((node) => attr(node, 'class') === 'vehicleVariant');
    assert(link && heading, 'Visible catalog card identity required');
    return { '@type': 'ListItem', position: index + 1, url: new URL(attr(link, 'href'), origin).href,
      name: [text(heading), variant ? text(variant) : ''].filter(Boolean).join(' ') };
  });
  target.list.numberOfItems = items.length;
  target.list.itemListElement = items.slice(0, 12);
  const location = target.script.sourceCodeLocation;
  return html.slice(0, location.startTag.endOffset) + safePageData(target.payload) + html.slice(location.endTag.startOffset);
}

export function replaceRoot(html, content, data) {
  const tree = parse(html, { sourceCodeLocationInfo: true });
  const queue = [tree], roots = [];
  while (queue.length) {
    const node = queue.pop();
    if (node.tagName === 'div' && node.attrs?.some((attr) => attr.name === 'id' && attr.value === 'root')) roots.push(node);
    queue.push(...(node.childNodes || []));
  }
  assert.equal(roots.length, 1, 'Exactly one application root required');
  const location = roots[0].sourceCodeLocation;
  assert(location?.endTag, 'Application root must have an end tag');
  const bootstrap = `<script type="application/json" id="public-page-data">${safePageData(data)}</script>`;
  return html.slice(0, location.startTag.endOffset) + content + html.slice(location.endTag.startOffset).replace('</body>', bootstrap + '\n</body>');
}

async function main() {
  const snapshot = JSON.parse(await readFile('public/data/public_ev_variants.json', 'utf8'));
  const news = JSON.parse(await readFile('public/data/news_articles.json', 'utf8'));
  assert(Array.isArray(news.records) && news.records.every(isPublishedArticle), 'Invalid public news snapshot');
  assert(snapshot.source === 'supabase_public_ev_variants' && snapshot.records?.length, 'Validated canonical snapshot required');
  assert(snapshot.records.every((row) => ['published', 'published_reviewed'].includes(row.validation_status) && row.source_hash && /^https:\/\//.test(row.source_url || '')), 'Unpublished or unsourced car');
  const sitemap = await readFile('public/sitemap.xml', 'utf8');
  const origin = (process.env.SITE_URL || 'https://elbilsagenten.se').replace(/\/$/, '');
  // Vite's SSR loader transforms the existing components without opening an HTTP listener.
  const server = await createServer({ mode: 'production', server: { middlewareMode: true, hmr: false, watch: null }, optimizeDeps: { noDiscovery: true, include: [] }, appType: 'custom' });
  try {
    const { renderPublicPage } = await server.ssrLoadModule('/src/entry-server.jsx');
    const paths = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => new URL(match[1]));
    for (const url of paths) {
      assert.equal(url.origin, origin, 'Unexpected sitemap origin');
      const path = url.pathname;
      const file = path === '/' ? 'dist/index.html' : `dist/${path.replace(/^\/|\/$/g, '')}/index.html`;
      const html = await readFile(file, 'utf8');
      const initialData = { path, records: snapshot.records, articles: publicArticles(news.records) };
      const content = renderPublicPage(initialData);
      assert(content.includes('<h1') && content.includes('<main'), 'Missing public page content: ' + path);
      const metadata = synchronizeItemList(html, content, origin);
      const rendered = replaceRoot(metadata, content, initialData).replace('</head>', `<meta name="public-content-version" content="${PUBLIC_CONTENT_VERSION}" /></head>`);
      await writeFile(file, rendered);
    }
    console.log(JSON.stringify({ rendered_public_pages: paths.length, source: snapshot.source, paid_calls: 0 }));
  } finally { await server.close(); }
}

if (process.argv[1]?.replaceAll('\\', '/').endsWith('/render_public_pages.mjs')) {
  main().catch((error) => { console.error(error); process.exitCode = 1; });
}
