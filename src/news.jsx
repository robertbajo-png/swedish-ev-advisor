import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Check, Copy, ExternalLink, Newspaper, RotateCcw, Sparkles, X } from 'lucide-react';
import { NEWS_CATEGORIES, NEWS_TOPICS, approvedNewsImage, articleBlocks, isPublishedArticle, newsDate, newsReadingMinutes, publicArticles, relatedNews, safeNewsLink } from './news-presentation.js';
import './news.css';

export { NEWS_CATEGORIES } from './news-presentation.js';

export function useNews(basePath = '') {
  const [state, setState] = useState({ articles: [], loading: true, error: false });
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      const url = import.meta.env.VITE_SUPABASE_URL;
      const key = import.meta.env.VITE_SUPABASE_ANON_KEY;
      if (url && key) {
        try {
          const response = await fetch(`${url}/rest/v1/public_news_articles?select=id,slug,published_at,payload&order=published_at.desc&limit=100`, {
            headers: { apikey: key, Authorization: `Bearer ${key}` }, signal: controller.signal
          });
          if (!response.ok) throw new Error('news_unavailable');
          return (await response.json()).map(({ payload, ...row }) => ({ ...payload, ...row }));
        } catch (error) { if (controller.signal.aborted) throw error; }
      }
      const response = await fetch(`${basePath}/data/news_articles.json`, { signal: controller.signal });
      if (!response.ok) throw new Error('news_unavailable');
      return (await response.json()).records || [];
    }
    load().then((articles) => {
      if (!controller.signal.aborted) setState({ articles, loading: false, error: false });
    }).catch(() => {
      if (!controller.signal.aborted) setState({ articles: [], loading: false, error: true });
    });
    return () => controller.abort();
  }, [basePath]);
  return state;
}

export function newsJsonLd(article, siteUrl) {
  if (!isPublishedArticle(article)) return null;
  const image = approvedNewsImage(article);
  return {
    '@context': 'https://schema.org', '@type': 'NewsArticle',
    headline: article.title, description: article.intro, datePublished: article.published_at,
    inLanguage: 'sv-SE', url: siteUrl + '/nyheter/' + article.slug,
    author: { '@type': 'Organization', name: 'Elbilsagenten' },
    publisher: { '@type': 'Organization', name: 'Elbilsagenten' },
    citation: (article.sources || []).filter((source) => safeNewsLink(source.url)).map((source) => source.url),
    articleBody: [article.intro, ...(article.paragraphs || []).map((paragraph) => paragraph.text)].join('\n\n'),
    ...(image ? { image: image.url } : {})
  };
}

function NewsLink({ path, navigate, children, className, ...props }) {
  const base = (import.meta.env.VITE_APP_BASE_PATH || '').replace(/\/$/, '');
  return <a {...props} className={className} href={base + path} onClick={(event) => {
    if (!event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) {
      event.preventDefault();
      navigate(path);
    }
  }}>{children}</a>;
}

function NewsImage({ article, priority = false, caption = false, onUnavailable }) {
  const [failedUrl, setFailedUrl] = useState(null);
  const image = approvedNewsImage(article);
  if (!image || failedUrl === image.url) return null;
  return <figure className="journalImage">
    <img src={image.url} alt={image.alt} loading={priority ? 'eager' : 'lazy'} fetchPriority={priority ? 'high' : 'auto'} decoding="async" onError={() => { setFailedUrl(image.url); onUnavailable?.(); }} />
    {caption && <figcaption><span>Bild: {image.credit}</span><a href={image.source_url} target="_blank" rel="noreferrer">Bildkälla <ArrowUpRight size={12} /></a><a href={image.license_url} target="_blank" rel="noreferrer">Bildvillkor <ArrowUpRight size={12} /></a></figcaption>}
  </figure>;
}

function NewsMeta({ article, readingTime = false }) {
  return <div className="newsMeta">
    <span>{NEWS_CATEGORIES[article.category] || 'Elbilar'}</span>
    <time dateTime={article.published_at}>{newsDate(article.published_at)}</time>
    {readingTime && <span className="newsReadingTime"><BookOpen size={13} /> Ca {newsReadingMinutes(article)} min läsning</span>}
  </div>;
}

function NewsCard({ article, navigate, variant = 'teaser', headingLevel = 3, priority = false }) {
  const [failedUrl, setFailedUrl] = useState(null);
  const Heading = 'h' + headingLevel;
  const image = approvedNewsImage(article);
  const hasImage = !!image && failedUrl !== image.url;
  const publishers = [...new Set((article.sources || []).map((source) => source.publisher).filter(Boolean))].slice(0, 2);
  return <article className={'newsStory newsStory--' + variant + (hasImage ? ' newsStory--withMedia' : '')}>
    {hasImage && <NewsLink className="newsStoryImageLink" path={'/nyheter/' + article.slug} navigate={navigate} aria-label={'Läs: ' + article.title}><NewsImage article={article} priority={priority} onUnavailable={() => setFailedUrl(image.url)} /></NewsLink>}
    <div className="newsStoryContent">
      <NewsMeta article={article} />
      <Heading className="newsStoryTitle"><NewsLink path={'/nyheter/' + article.slug} navigate={navigate}>{article.title}</NewsLink></Heading>
      <p className="newsStoryIntro">{article.intro}</p>
      <div className="newsStoryFooter"><span>{publishers.join(' / ') || 'Elbilsagenten'}</span><NewsLink className="newsReadLink" path={'/nyheter/' + article.slug} navigate={navigate} aria-label={'Läs nyheten: ' + article.title}>Läs nyheten <ArrowUpRight size={16} /></NewsLink></div>
      {variant === 'lead' && !!article.related_models?.length && <div className="newsStoryModels"><span>Bilar i nyheten</span>{article.related_models.filter((model) => /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(model.car_slug || '')).slice(0, 2).map((model) => <NewsLink key={model.key} path={'/bilar/' + model.car_slug} navigate={navigate}>{model.brand} {model.model} <ArrowRight size={13} /></NewsLink>)}</div>}
    </div>
  </article>;
}

function NewsEmpty({ error, filtered, onReset, navigate }) {
  return <div className="newsEmpty">
    <Newspaper size={32} strokeWidth={1.4} aria-hidden="true" />
    <h2>{error ? 'Nyheterna kunde inte hämtas' : filtered ? 'Inga nyheter matchar ditt val' : 'Snart mer från elbilsvärlden'}</h2>
    <p>{error ? 'Försök igen om en stund.' : filtered ? 'Prova ett annat märke eller ämne.' : 'Det finns inga publicerade nyheter att visa ännu.'}</p>
    {error ? <button className="uiPrimary" type="button" onClick={() => window.location.reload()}><RotateCcw size={16} /> Försök igen</button> : filtered ? <button className="uiPrimary" type="button" onClick={onReset}>Visa alla nyheter <ArrowRight size={16} /></button> : <NewsLink className="homeTextLink" path="/bilar" navigate={navigate}>Utforska elbilar <ArrowRight size={16} /></NewsLink>}
  </div>;
}

function NewsLoading({ article = false }) {
  return <div className={'newsLoading ' + (article ? 'newsLoadingArticle' : '')} role="status">
    <p>{article ? 'Hämtar nyheten...' : 'Hämtar nyheter...'}</p>
    <div className="newsSkeletons" aria-hidden="true"><div /><div /><div /></div>
  </div>;
}

export function NewsPreview({ articles, navigate, title = 'Det senaste i elbilsvärlden', relatedKey, showEmpty = false, loading = false, error = false }) {
  const shown = publicArticles(articles).filter((article) => !relatedKey || (article.related_models || []).some((model) => model.key === relatedKey)).slice(0, 3);
  if (!shown.length && !showEmpty) return null;
  return <section className="newsPreview journalPreview" aria-label={title}>
    <div className="newsSectionHeading"><div><span className="journalEyebrow">Elbilsagenten Journal</span><h2>{title}</h2></div><NewsLink path="/nyheter" navigate={navigate}>Alla nyheter <ArrowRight size={17} /></NewsLink></div>
    {shown.length ? <div className="journalPreviewGrid">{shown.map((article) => <NewsCard key={article.id || article.slug} article={article} navigate={navigate} />)}</div> : <p className="newsPreviewEmpty" role="status">{loading ? 'Hämtar nyheter...' : error ? 'Nyheterna kunde inte hämtas just nu.' : 'Inga nyheter är publicerade ännu.'}</p>}
  </section>;
}

export function NewsPage({ articles, loading, error, navigate }) {
  const [brand, setBrand] = useState('Alla');
  const [topic, setTopic] = useState('all');
  const published = useMemo(() => publicArticles(articles), [articles]);
  const brands = useMemo(() => [...new Set(published.flatMap((article) => article.brands || []))].sort((a, b) => a.localeCompare(b, 'sv-SE')), [published]);
  const categories = NEWS_TOPICS.find((item) => item.id === topic)?.categories || [];
  const filtered = published.filter((article) => (brand === 'Alla' || (article.brands || []).includes(brand)) && (!categories.length || categories.includes(article.category)));
  const activeFilters = brand !== 'Alla' || topic !== 'all';
  const reset = () => { setBrand('Alla'); setTopic('all'); };

  return <section className="newsPage journalPage" aria-labelledby="journal-title">
    <header className="journalMasthead">
      <div><span className="journalEyebrow">Elbilsagenten Journal</span><h1 id="journal-title">Elbilsnyheter.</h1><p>Nya modeller, teknik och marknadsnyheter. Med svenska bilköpare i fokus.</p></div>
      {!!published.length && <div className="journalLastPublished"><span>Senast publicerat</span><time dateTime={published[0].published_at}>{newsDate(published[0].published_at)}</time></div>}
    </header>
    <div className="journalTopicNav" role="group" aria-label="Nyhetskategorier">{NEWS_TOPICS.map((item) => <button type="button" key={item.id} aria-pressed={topic === item.id} onClick={() => setTopic(item.id)} disabled={loading || !published.length}>{item.label}</button>)}</div>
    <div className="journalFilterRow">
      <label htmlFor="journal-brand">Märke<select id="journal-brand" aria-label="Märke" value={brand} onChange={(event) => setBrand(event.target.value)} disabled={loading || !published.length}><option>Alla</option>{brands.map((name) => <option key={name}>{name}</option>)}</select></label>
      <span role="status">{loading ? 'Hämtar nyheter' : filtered.length + (filtered.length === 1 ? ' nyhet' : ' nyheter')}</span>
      {activeFilters && <button type="button" className="journalReset" onClick={reset}><X size={14} /> Rensa filter</button>}
    </div>
    {loading ? <NewsLoading /> : !filtered.length ? <NewsEmpty error={error} filtered={!!published.length} onReset={reset} navigate={navigate} /> : <>
      <div className={'journalLeadLayout' + (filtered.length === 1 ? ' journalLeadLayout--solo' : '')}>
        <NewsCard article={filtered[0]} navigate={navigate} variant="lead" headingLevel={2} priority />
        {filtered.length > 1 && <div className="journalSecondary" aria-label="Fler aktuella nyheter">{filtered.slice(1, 3).map((article) => <NewsCard key={article.id || article.slug} article={article} navigate={navigate} variant="secondary" headingLevel={2} />)}</div>}
      </div>
      {filtered.length > 3 && <section className="journalRecent" aria-labelledby="journal-recent-title"><div className="newsSectionHeading"><div><span className="journalEyebrow">Fortsätt läsa</span><h2 id="journal-recent-title">Fler nyheter.</h2></div></div><div className="journalRecentGrid">{filtered.slice(3).map((article) => <NewsCard key={article.id || article.slug} article={article} navigate={navigate} variant="recent" />)}</div></section>}
    </>}
  </section>;
}

function ArticleSources({ article }) {
  const sources = (article.sources || []).filter((source) => safeNewsLink(source.url));
  return <section className="newsSources" aria-labelledby="article-sources-title" id="artikelkallor">
    <span className="journalEyebrow">Bakom nyheten</span><h2 id="article-sources-title">Källor och vidare läsning</h2>
    {sources.length ? <ol>{sources.map((source, index) => <li key={source.item_id || source.url}><a href={source.url} target="_blank" rel="noreferrer"><span className="journalSourceNumber">{String(index + 1).padStart(2, '0')}</span><span><strong>{source.publisher}: </strong>{source.title}</span><ExternalLink size={14} /></a>{source.published_at && <time dateTime={source.published_at}>{newsDate(source.published_at)}</time>}</li>)}</ol> : <p>Källhänvisningar saknas i underlaget.</p>}
  </section>;
}

function ArticleShare() {
  const [state, setState] = useState('idle');
  const copy = async () => {
    try { await navigator.clipboard.writeText(window.location.href); setState('copied'); }
    catch { setState('error'); }
  };
  return <div className="journalShare"><button type="button" title="Kopiera artikelns länk" onClick={copy}>{state === 'copied' ? <Check size={16} /> : <Copy size={16} />}{state === 'copied' ? 'Länk kopierad' : 'Kopiera länk'}</button><span role="status">{state === 'error' ? 'Länken kunde inte kopieras.' : state === 'copied' ? 'Artikelns länk är kopierad.' : ''}</span></div>;
}

function ArticleVehicles({ article, cars = [], navigate, renderVehicleCard }) {
  const models = [...new Map((article.related_models || []).filter((model) => /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(model.car_slug || '')).map((model) => [model.key, model])).values()];
  if (!models.length) return null;
  return <section className="newsRelated" aria-labelledby="article-vehicles-title">
    <div className="newsSectionHeading"><div><span className="journalEyebrow">Från nyhet till bilval</span><h2 id="article-vehicles-title">Bilar i nyheten</h2></div><NewsLink path="/jamfor" navigate={navigate}>Jämför elbilar <ArrowRight size={17} /></NewsLink></div>
    <div className="journalVehicleGrid">{models.map((model) => {
      const car = cars.find((candidate) => candidate.id === model.car_slug && candidate.canonicalKey?.split('|').slice(0, 2).join('|') === model.key);
      return car && renderVehicleCard ? <React.Fragment key={model.key}>{renderVehicleCard(car)}</React.Fragment> : <NewsLink className="newsRelatedModel" key={model.key} path={'/bilar/' + model.car_slug} navigate={navigate}><span><strong>{model.brand} {model.model}</strong><small>Pris, räckvidd och specifikationer</small></span><ArrowUpRight size={20} /></NewsLink>;
    })}</div>
  </section>;
}

export function NewsArticlePage({ article, articles = [], loading, error, navigate, cars = [], renderVehicleCard }) {
  if (loading) return <section className="newsPage"><NewsLoading article /></section>;
  if (error) return <section className="newsPage"><NewsEmpty error navigate={navigate} /></section>;
  if (!isPublishedArticle(article)) return <section className="newsPage newsEmpty"><Newspaper size={32} /><h1>Nyheten hittades inte</h1><NewsLink className="homeTextLink" path="/nyheter" navigate={navigate}>Till alla nyheter <ArrowRight size={16} /></NewsLink></section>;
  const blocks = articleBlocks(article);
  const more = relatedNews(article, articles);
  return <article className="newsArticlePage journalArticle">
    <div className="journalArticleTop"><NewsLink className="newsBackLink" path="/nyheter" navigate={navigate}><ArrowLeft size={16} /> Alla nyheter</NewsLink><span className="journalEyebrow">Elbilsagenten Journal</span></div>
    <header className="newsArticleHeader"><NewsMeta article={article} readingTime /><h1>{article.title}</h1><p>{article.intro}</p><div className="journalByline"><span>Elbilsagenten{article.editorial_method ? ' · ' + article.editorial_method : ''}</span><ArticleShare key={article.id || article.slug} /></div></header>
    <NewsImage article={article} priority caption />
    <div className="journalReadingLayout">
      <div className="newsArticleBody">{blocks.map((block, index) => <section key={index} className={block.kind === 'analysis' ? 'journalBuyerPerspective' : 'journalReporting'} aria-label={block.kind === 'analysis' ? 'Köparperspektiv' : undefined}>{block.kind === 'analysis' && <><span className="journalEyebrow"><Sparkles size={14} /> Köparperspektiv</span><h2>Vad betyder detta för dig som bilköpare?</h2></>}{block.paragraphs.map((text, paragraphIndex) => <p key={paragraphIndex}>{text}</p>)}</section>)}</div>
      <aside className="journalArticleAside"><ArticleSources article={article} /></aside>
    </div>
    <ArticleVehicles article={article} cars={cars} navigate={navigate} renderVehicleCard={renderVehicleCard} />
    {!!more.length && <section className="journalMore" aria-labelledby="journal-more-title"><div className="newsSectionHeading"><div><span className="journalEyebrow">Fler perspektiv</span><h2 id="journal-more-title">Mer att läsa.</h2></div><NewsLink path="/nyheter" navigate={navigate}>Alla nyheter <ArrowRight size={17} /></NewsLink></div><div className="journalPreviewGrid">{more.map((item) => <NewsCard key={item.id || item.slug} article={item} navigate={navigate} />)}</div></section>}
  </article>;
}
