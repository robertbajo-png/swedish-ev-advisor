export const NEWS_CATEGORIES = {
  modeller: 'Nya elbilar', priser: 'Priser', batterier: 'Teknik & batterier', laddning: 'Laddning',
  tester: 'Tester', marknad: 'Marknad', uppdateringar: 'Modelluppdateringar', sakerhet: 'Säkerhet'
};

export const NEWS_TOPICS = [
  { id: 'all', label: 'Alla nyheter', categories: [] },
  { id: 'modeller', label: 'Nya elbilar', categories: ['modeller', 'uppdateringar'] },
  { id: 'teknik', label: 'Teknik & batterier', categories: ['batterier', 'sakerhet'] },
  { id: 'tester', label: 'Tester', categories: ['tester'] },
  { id: 'marknad', label: 'Priser & marknad', categories: ['priser', 'marknad'] },
  { id: 'laddning', label: 'Laddning', categories: ['laddning'] },
];

export function safeNewsLink(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password;
  } catch { return false; }
}

export function isPublishedArticle(article) {
  return !!article && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(article.slug || '') &&
    typeof article.title === 'string' && !!article.title.trim() &&
    !!article.published_at && Number.isFinite(Date.parse(article.published_at)) &&
    (!article.status || article.status === 'published');
}

export function publicArticles(articles = []) {
  return articles.filter(isPublishedArticle).slice().sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at));
}

export function newsDate(value) {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Datum saknas';
  return new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Europe/Stockholm' }).format(new Date(value));
}

export function newsReadingMinutes(article) {
  const text = [article.intro || '', ...(article.paragraphs || []).map((paragraph) => paragraph.text || '')].join(' ');
  return Math.max(1, Math.ceil(text.trim().split(/\s+/).filter(Boolean).length / 200));
}

export function approvedNewsImage(article) {
  const image = article?.image;
  if (!image || typeof image !== 'object' || image.rights_status !== 'approved' ||
    !safeNewsLink(image.url) || !safeNewsLink(image.source_url) || !safeNewsLink(image.license_url) ||
    !String(image.alt || '').trim() || !String(image.credit || '').trim()) return null;
  return image;
}

export function articleBlocks(article) {
  const blocks = [];
  for (const paragraph of article.paragraphs || []) {
    if (typeof paragraph.text !== 'string' || !paragraph.text.trim()) continue;
    const kind = paragraph.kind === 'analysis' ? 'analysis' : 'reporting';
    const previous = blocks.at(-1);
    if (previous?.kind === kind) previous.paragraphs.push(paragraph.text);
    else blocks.push({ kind, paragraphs: [paragraph.text] });
  }
  return blocks;
}

export function relatedNews(article, articles = []) {
  const brands = new Set(article.brands || []);
  const models = new Set((article.related_models || []).map((model) => model.key));
  const score = (candidate) => (candidate.related_models || []).some((model) => models.has(model.key)) ? 3 :
    (candidate.brands || []).some((brand) => brands.has(brand)) ? 2 : candidate.category === article.category ? 1 : 0;
  return publicArticles(articles).filter((item) => item.slug !== article.slug).sort((a, b) => score(b) - score(a)).slice(0, 3);
}
