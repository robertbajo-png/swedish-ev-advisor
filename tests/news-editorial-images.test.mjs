import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { editorialNewsImage } from '../src/news-editorial-images.js';
import photos from '../src/news-editorial-images.json' with { type: 'json' };

const makeArticle = (slug, id) => ({ slug, id, title: 'Nyhet', published_at: '2026-11-24T04:04:43Z' });

test('editorial photos have reviewed local bytes and belong to one published article', async () => {
  assert.ok(Object.keys(photos).length);
  const files = new Set();
  for (const [slug, photo] of Object.entries(photos)) {
    const article = makeArticle(slug, photo.article_id);
    assert.equal(editorialNewsImage(article), photo);
    assert.equal(editorialNewsImage({ ...article, id: 'another-article' }), null);
    assert.equal(editorialNewsImage({ ...article, slug: 'another-article' }), null);
    assert.equal(editorialNewsImage({ ...article, status: 'draft' }), null);
    assert.match(photo.url, /^\/media\/(news|responsive)\/[a-z0-9-]+\.webp$/);
    assert.ok(!files.has(photo.url), 'Bind each photo independently');
    files.add(photo.url);
    assert.ok(photo.width > 0 && photo.height > 0);
    assert.ok(photo.alt && photo.caption && photo.credit && photo.license_name && photo.edits);
    for (const link of [photo.source_url, photo.license_url]) assert.equal(new URL(link).protocol, 'https:');
    const bytes = await readFile(new URL('../public' + photo.url, import.meta.url));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), photo.sha256);
  }
});

test('an approved article photo takes precedence and unrelated articles stay photo-free', () => {
  const approved = {
    rights_status: 'approved', url: 'https://example.com/photo.jpg', alt: 'Foto',
    credit: 'Fotograf', source_url: 'https://example.com/source', license_url: 'https://example.com/rights',
  };
  const [slug, photo] = Object.entries(photos)[0];
  const article = makeArticle(slug, photo.article_id);
  assert.equal(editorialNewsImage({ ...article, image: approved }), approved);
  assert.equal(editorialNewsImage({ ...article, image: { ...approved, rights_status: 'pending' } }), photo);
  assert.equal(editorialNewsImage(makeArticle('unrelated-story','not-registered')), null);
});
