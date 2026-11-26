
import React, { useEffect } from 'react';
import { publicArticles, safeNewsLink } from './news-presentation.js';
import { editorialNewsImage } from './news-editorial-images.js';
import { coverPhoto, photoCredit } from './biljournal-images.js';
import { assetPath, isOfflineReview } from './preview-paths.js';
import responsive from './image-variants.json';
import { featuredCarsForHome, featuredHomePhoto } from './home-featured-photos.js';

export function variantSourcePath(id) {
  return '/kallor?post=bil-' + encodeURIComponent(id);
}
export function articleSourcePath(slug) {
  return '/kallor?post=artikel-' + encodeURIComponent(slug);
}

const costSources = [
  ['Konsumentverket · privatleasing','https://www.konsumentverket.se/varor-och-tjanster/leasa-bil-tips/','Avtalstid, avgifter, övermil och vad som ingår.'],
  ['Konsumenternas · billån','https://konsumenternasbankochfinansbyra.se/lan--betalningar/lan/konsumtionslan/billan-och-fordonslan','Kontantinsats, amortering och låneavgifter.'],
  ['Transportstyrelsen · fordonsskatt','https://www.transportstyrelsen.se/sv/vagtrafik/fordon/skatter-och-avgifter/fordonsskatt/skattens-storlek/','Sök faktisk skatt för fordonet.'],
  ['Energimyndigheten · laddpriser','https://www.energimyndigheten.se/nyhetsarkiv/2026/stora-prisskillnader-for-elbilsladdning-beroende-pa-boendeform/','Laddplats och pris påverkar driften. Kalkylens elpriser är antaganden.'],
];

function External({ url, children }) {
  return safeNewsLink(url) ? <a href={url} target="_blank" rel="noreferrer">{children}</a> : null;
}

function Photos({ cars, articles }) {
  const photos = new Map();
  function add(key, photo, context) {
    if (!photo || !safeNewsLink(photo.source_url) || !safeNewsLink(photo.license_url)) return;
    if (!photos.has(key)) photos.set(key, { photo, contexts: new Set() });
    photos.get(key).contexts.add(context);
  }
  // The contextual link to Bildkrediter leads directly to the current three
  // homepage photographs; model-view and article credits follow as before.
  for (const car of featuredCarsForHome(cars, true)) {
    const alternate = featuredHomePhoto(car);
    if (car.image) add(alternate?.asset_url || car.image, alternate || photoCredit(car.image), car.brand+' '+car.canonicalModel+' · startsidans bilurval');
  }
  for (const car of cars) {
    if (!car.image) continue;
    const candidate = !car.imageFullFrame && responsive[car.image]?.variants.find(item => item.width >= 800)?.url;
    if (!isOfflineReview() || assetPath(candidate || car.image)) add(car.image,photoCredit(car.image),car.brand+' '+car.model+' · modellvyer');
  }
  for (const article of articles) {
    const image = editorialNewsImage(article);
    if (image && (!isOfflineReview() || assetPath(image.url))) add(image.url,{ ...image, title: image.caption || image.alt, license_id: image.license_name, changes: image.edits },article.title);
  }
  return <section aria-labelledby="bilder"><h2 id="bilder" tabIndex={-1}>Bildkrediter</h2>
    <ul className="bilSourcesList">{[...photos].map(([key,{photo,contexts}]) =>
      <li key={key}><h3>{photo.title || [...contexts][0]}</h3><p>{photo.credit || photo.author} · <External url={photo.source_url}>Bildkälla</External> · <External url={photo.license_url}>{photo.license_id || 'Bildvillkor'}</External></p>
        <p>{[...contexts].join(' · ')}</p>
        {photo.changes && <p>{photo.changes}</p>}
        {key === coverPhoto && <p>Fotot visar Hyundai Inster Prime. Motivet visas i helbild på modellsidan.</p>}
      </li>)}</ul></section>;
}

function VariantEvidence({ car }) {
  const sources = [
    {url:car.source,label:car.sourceName || 'Bilens faktakälla'},
    ...(car.practicalSource ? [{url:car.practicalSource,label:'Bagagevolym och mätvillkor'}] : []),
    ...(car.specSources || []),
  ];
  const unique = [...new Map(sources.filter(s=>safeNewsLink(s.url)).map(s=>[s.url,s])).values()];
  return <li className="bilSourceItem"><h4 id={'bil-'+car.id} tabIndex={-1}>{car.brand} {car.model} · {car.variantName}</h4>
    {car.verifiedAt && <p>Biluppgifter kontrollerade <time dateTime={car.verifiedAt}>{car.verifiedAt}</time>.</p>}
    {car.priceSource && <p><External url={car.priceSource}>{car.priceSourceName || 'Priskälla'}</External>
      {car.priceVerifiedAt && <> · pris kontrollerat <time dateTime={car.priceVerifiedAt}>{car.priceVerifiedAt}</time></>}
      {car.priceValidUntil && <> · giltigt t.o.m. <time dateTime={car.priceValidUntil}>{car.priceValidUntil}</time></>}</p>}
    <ul>{unique.map(s=><li key={s.url}><External url={s.url}>{s.label}</External></li>)}</ul>
    {(car.sourceHash || car.priceSourceHash || car.sourceQuote || car.priceSourceQuote) && <details><summary>Källbevis</summary>
      {car.sourceQuote && <p>{car.sourceQuote}</p>}
      {car.sourceHash && <p>SHA-256, biluppgifter <code>{car.sourceHash}</code></p>}
      {car.priceSourceQuote && <p>{car.priceSourceQuote}</p>}
      {car.priceSourceHash && <p>SHA-256, pris <code>{car.priceSourceHash}</code></p>}
    </details>}</li>;
}

export function BiljournalSources({ cars, articles, target, link }) {
  const published = publicArticles(articles);
  useEffect(() => {
    const heading = target ? document.getElementById(target) : null;
    if (heading) {
      heading.focus({preventScroll:true});
      heading.scrollIntoView({block:'start'});
    }
  },[target,cars.length,published.length]);
  return <div className="bilSources bilWidth">
    <h1>Källor och bildkrediter</h1><p>Här finns uppgifternas originalkällor, kontrolldatum och villkoren för bilderna.</p>
    <nav aria-label="På källsidan">{link('/kallor?post=artiklar','Artiklar')}{link('/kallor?post=bilfakta','Bilfakta och priser')}{link('/kallor?post=kalkyl','Kalkylmetod')}{link('/kallor?post=bilder','Bildkrediter')}</nav>
    <section aria-labelledby="kallor"><h2 id="kallor" tabIndex={-1}>Källor</h2>
      <h3 id="artiklar" tabIndex={-1}>Artiklar</h3>
      <ul className="bilSourcesList">{published.map(article => <li key={article.id}><h4 id={'artikel-'+article.slug} tabIndex={-1}>{article.title}</h4>
        <ul>{(article.sources || []).filter(source=>safeNewsLink(source.url)).map((source,index)=>
          <li key={source.item_id || source.url+index}><External url={source.url}>{source.publisher ? source.publisher + ': ' : ''}{source.title || 'Originalkälla'}</External>
            {source.published_at && <> · <time dateTime={source.published_at}>{source.published_at.slice(0,10)}</time></>}</li>)}</ul></li>)}</ul>
      <h3 id="bilfakta" tabIndex={-1}>Bilfakta och priser</h3>
      <ul className="bilSourcesList">{cars.map(car=><VariantEvidence key={car.id} car={car} />)}</ul>
      <h3 id="kalkyl" tabIndex={-1}>Kalkylmetod</h3>
      <p>Pris och WLTP hämtas från respektive variant där underlag finns. Drift, försäljningsvärde och egna avtalsvillkor är antaganden.</p>
      <ul className="bilSourcesList">{costSources.map(([label,url,note])=><li key={url}><External url={url}>{label}</External><p>{note}</p></li>)}</ul>
    </section>
    <Photos cars={cars} articles={published} />
    {isOfflineReview() && <section aria-labelledby="typsnitt"><h2 id="typsnitt">Typsnitt</h2>
      <details><summary>Newsreader och Manrope · SIL Open Font License</summary>
        <pre className="bilFontLicense">{JSON.parse(document.getElementById('font-licenses')?.textContent || '[]').join('\n\n')}</pre>
      </details>
    </section>}
  </div>;
}
