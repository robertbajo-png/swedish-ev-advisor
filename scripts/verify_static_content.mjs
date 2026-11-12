import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { parse } from 'parse5';
import { safePageData, replaceRoot, synchronizeItemList } from './render_public_pages.mjs';
import { isPublishedArticle } from '../src/news-presentation.js';

const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const raw = { text: '</script><script>alert(1)</script>&\u2028', records: [] };
assert(!safePageData(raw).includes('<'));
assert.deepEqual(JSON.parse(safePageData(raw)), raw);
const replaced = replaceRoot('<html><body><div id="root"><div>Old nested content</div></div><footer>Keep</footer></body></html>', '<main><h1>New</h1></main>', raw);
assert(!replaced.includes('Old nested')); assert(replaced.includes('<footer>Keep</footer>'));
const listFixture = '<script type="application/ld+json" data-prerender="page">[{"@type":"ItemList","numberOfItems":99,"itemListElement":[]}]</script>';
const fixed = synchronizeItemList(listFixture, '<article class="vehicleCard"><h2><a href="/bilar/synthetic">Synthetic &amp; Model</a></h2><p class="vehicleVariant">Exact variant</p></article>', 'https://elbilsagenten.se');
assert(fixed.includes('"numberOfItems":1'));
assert(fixed.includes('Exact variant'));
const groupedFixture = synchronizeItemList(listFixture, '<article class="vehicleCard"><h2><a href="/bilar/synthetic-long-range">Synthetic Model</a></h2><label class="vehicleVariantPicker"><select><option>Base</option><option selected="">Long Range</option></select></label></article>', 'https://elbilsagenten.se');
assert(groupedFixture.includes('Synthetic Model Long Range'), 'Structured list uses the actual visible selected version');
assert(!groupedFixture.includes('Synthetic Model Base'));

const rights = JSON.parse(await readFile('src/image-rights.json', 'utf8'));
const variants = JSON.parse(await readFile('src/image-variants.json', 'utf8'));
for (const [source, image] of Object.entries(variants)) {
  const original = rights.assets.find((asset) => asset.asset_url === source && asset.status === 'documented');
  assert(original && original.content_sha256 === image.source_sha256, 'Unlicensed or mismatched original');
  assert.equal(hash(await readFile('public' + source)), image.source_sha256);
  for (const variant of image.variants) {
    assert(variant.width <= image.width && variant.url.startsWith('/media/responsive/'));
    const bytes = await readFile('public' + variant.url);
    assert.equal(hash(bytes), variant.sha256);
    assert.equal(bytes.toString('ascii', 8, 12), 'WEBP');
  }
}
const png = await readFile('public/media/elbilsguiden-share.png');
assert.equal(png.readUInt32BE(16), 1200); assert.equal(png.readUInt32BE(20), 630);
const sitemap = await readFile('public/sitemap.xml', 'utf8');
let pages = 0;
for (const match of sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)) {
  const path = new URL(match[1]).pathname;
  const file = path === '/' ? 'dist/index.html' : 'dist' + path + '/index.html';
  const html = await readFile(file, 'utf8');
  const queue = [parse(html)], nodes = [];
  while (queue.length) { const node = queue.pop(); nodes.push(node); queue.push(...(node.childNodes || [])); }
  const attr = (node, name) => node.attrs?.find((item) => item.name === name)?.value;
  assert.equal(nodes.filter((node) => node.tagName === 'h1').length, 1, path + ': one visible main heading');
  assert(nodes.filter((node) => node.tagName === 'a' && attr(node, 'href')?.startsWith('/')).length >= 6, path + ': real internal links');
  const data = nodes.find((node) => attr(node, 'id') === 'public-page-data');
  assert(data, path + ': missing hydration snapshot');
  const initial = JSON.parse(data.childNodes.map((node) => node.value || '').join(''));
  assert.equal(initial.path, path);
  assert(initial.records.every((row) => ['published', 'published_reviewed'].includes(row.validation_status)));
  assert(initial.articles.every(isPublishedArticle));
  if (path.startsWith('/nyheter/')) {
    const article = initial.articles.find((row) => path === '/nyheter/' + row.slug);
    assert(article && html.includes(article.title), 'Actual published article required, not a missing-article state');
    assert(!html.includes('Nyheten hittades inte'), path + ': missing article');
  }
  assert(nodes.some((node) => attr(node, 'property') === 'og:image' && attr(node, 'content')?.endsWith('/media/elbilsguiden-share.png')));
  if (['/familj', '/vinter', '/dragkrok', '/under-500000', '/lang-rackvidd'].includes(path)) {
    assert(nodes.some((node) => attr(node, 'class') === 'needGuide'), path + ': missing useful guide');
    const jsonLd = nodes.find((node) => attr(node, 'data-prerender') === 'page');
    const list = JSON.parse(jsonLd.childNodes.map((node) => node.value || '').join('')).find((node) => node['@type'] === 'ItemList');
    assert.equal(list.numberOfItems, nodes.filter((node) => node.tagName === 'article' && (attr(node, 'class') || '').split(' ').includes('vehicleCard')).length,
      path + ': structured list must match visible variants');
  }
  pages++;
}
console.log(JSON.stringify({ static_pages_checked: pages, licensed_exact_model_images: Object.keys(variants).length, script_escape_tests: true, paid_calls: 0 }));
