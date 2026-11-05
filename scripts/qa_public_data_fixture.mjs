import assert from 'node:assert/strict';
import { parse } from 'parse5';

// Transport-fixture suites exercise client loading/error paths. Real SSR and
// hydration are covered separately by verify_public_content_ui with no rewrites.
export async function isolatePublicDataFixture(page) {
  await page.route('**/*', async (route) => {
    if (route.request().resourceType() !== 'document') return route.continue();
    const response = await route.fetch();
    if (!response.headers()['content-type']?.includes('text/html')) return route.fulfill({ response });
    const html = await response.text();
    const edits = [];
    let rootFound = false;
    const visit = (node) => {
      const id = node.attrs?.find((attr) => attr.name === 'id')?.value;
      if (id === 'root') {
        rootFound = true;
        const location = node.sourceCodeLocation;
        edits.push({ start: location.startTag.endOffset, end: location.endTag.startOffset });
      } else if (id === 'public-page-data') {
        const location = node.sourceCodeLocation;
        edits.push({ start: location.startOffset, end: location.endOffset });
      }
      for (const child of node.childNodes || []) visit(child);
    };
    visit(parse(html, { sourceCodeLocationInfo: true }));
    assert(rootFound, 'UI transport fixture requires the application shell');
    let body = html;
    for (const { start, end } of edits.sort((a, b) => b.start - a.start)) body = body.slice(0, start) + body.slice(end);
    await route.fulfill({ response, body });
  });
}
