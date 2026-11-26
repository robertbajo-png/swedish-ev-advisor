import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, ArrowUpRight, Check, ChevronDown, GitCompareArrows, MountainSnow, PlugZap, Route, Search, SlidersHorizontal, Sparkles, Users, WalletCards, Weight, Crown } from 'lucide-react';
import './home.css';
import { BiljournalWeek } from './biljournal-home.jsx';
import { browseCarCoverage, featuredCarsForHome, useFeaturedHomePhoto } from './home-featured-photos.js';
import { VehicleLink, VehicleCard as HomeVehicleCard, vehiclePriceLabel } from './vehicle-ui.jsx';
import { preferredScrollBehavior } from './ui-navigation.js';
import { VehicleImageNotice } from './vehicle-image-notice.jsx';

// These three full-frame editorial assets have the same documented,
// non-image-specific model notice. Other rights or notices stay on each card.
const sharedPressNoticeAssets = new Set([
  '/media/vehicles/bmw-i4-press-497a46b16ded.jpg',
  '/media/vehicles/bmw-i4-press-0f228bbc4a06.jpg',
  '/media/vehicles/cupra-born-press-7b71951e205b.jpg',
  '/media/vehicles/ford-explorer-press-050047452e4e.jpg',
  '/media/vehicles/ford-explorer-press-96d1dbd59dc4.jpg',
]);
const genericPressNotice = 'Pressbild. Utrustning kan skilja mellan versioner.';
const featuredNoticeId = 'home-featured-image-notice';

const money = (value) => new Intl.NumberFormat('sv-SE').format(value) + ' kr';
const metric = (value, unit) => value == null ? 'Uppgift saknas' : `${value} ${unit}`;
const suggestions = [
  { label: 'Mest räckvidd för pengarna', icon: Route, prompt: 'Jag söker en elbil med så lång räckvidd som möjligt för pengarna.', need: 'pendling' },
  { label: 'Bästa familjeelbilen', icon: Users, prompt: 'Jag söker en familjeelbil med gott om bagageutrymme och plats för två barn.', need: 'familj' },
  { label: 'Fyrhjulsdrift', icon: MountainSnow, prompt: 'Jag söker en elbil med fyrhjulsdrift för vardag och vinterresor.', need: 'vinter' },
  { label: 'Snabbladdning', icon: PlugZap, prompt: 'Jag söker en elbil för långresor med snabb DC-laddning.', need: 'langresa' },
  { label: 'Elbil med dragkrok', icon: Weight, prompt: 'Jag söker en elbil med dragkrok och verifierad dragvikt.', need: 'familj' },
];
const categories = [
  { title: 'Familj', text: 'Plats för hela vardagen', icon: Users, path: '/familj' },
  { title: 'Långresor', text: 'Lite längre på en laddning', icon: Route, path: '/lang-rackvidd' },
  { title: 'Budget', text: 'Bilar under 500 000 kr', icon: WalletCards, path: '/under-500000' },
  { title: 'Fyrhjulsdrift', text: 'För alla årstider', icon: MountainSnow, prompt: suggestions[2] },
  { title: 'Dragkrok', text: 'Ta med lite mer', icon: Weight, path: '/dragkrok' },
  { title: 'Premium', text: 'Hitta dina prioriteringar', icon: Crown, prompt: { prompt: 'Jag söker en premiumelbil och vill jämföra räckvidd, laddning och praktiska kompromisser.', need: 'langresa' } },
];
const needNames = { familj: 'Familj', vinter: 'Vinter', pendling: 'Vardag & pendling', langresa: 'Långresor', budget: 'Budget', dragkrok: 'Dragkrok', allround: 'Vardag' };


export function HomePage({ drivingWeek, localAdvisor = false, cars, dataStatus, advisor, setAdvisor, result, status, submittedAdvisor, onSubmit, compare, onCompare, navigate, appPath, renderImage, newsPreview }) {
  const [advanced, setAdvanced] = useState(false);
  const weekFocusRequested = useRef(false);
  const weekOpen = drivingWeek?.open;
  useEffect(() => {
    if (!weekOpen || !weekFocusRequested.current) return;
    weekFocusRequested.current = false;
    const title = document.getElementById('bil-week-title');
    title?.focus({ preventScroll: true });
    title?.scrollIntoView({ behavior: preferredScrollBehavior(), block: 'nearest' });
  }, [weekOpen]);
  useEffect(() => {
    if (status.state === 'loading') document.getElementById('dina-forslag')?.scrollIntoView({ behavior: preferredScrollBehavior(), block: 'start' });
  }, [status.state]);
  // Browse previews favour complete records and different brands, not a personalised ranking.
  const browseCars = [...cars].sort((a, b) => browseCarCoverage(b) - browseCarCoverage(a));
  const spotlight = browseCars.find((car) => car.image) || cars[0];
  // Same selected variants, with separate home-only full-frame photo choices.
  const chosen = featuredCarsForHome(cars, Boolean(drivingWeek));
  const featured = drivingWeek ? chosen.map(useFeaturedHomePhoto) : chosen;
  const shareFeaturedNotice = Boolean(drivingWeek && featured.length > 1 && featured.every(car =>
    car.imageFullFrame && sharedPressNoticeAssets.has(car.image) && car.imageNotice === genericPressNotice));
  const recommendations = (result?.shortlist || []).map((item) => {
    const key = item.canonicalKey || [item.brand, item.model, item.variant_name].join('|');
    const car = cars.find((candidate) => candidate.canonicalKey === key);
    return car ? { car, recommendation: item } : null;
  }).filter(Boolean).slice(0, 3);
  const interpreted = result?.interpreted_requirements || {};
  const requirements = submittedAdvisor ? [
    `Budget: ${money(interpreted.budget_sek ?? submittedAdvisor.budget)}`,
    `Räckvidd: minst ${interpreted.min_wltp_range_km ?? interpreted.min_range_km ?? submittedAdvisor.range} km`,
    needNames[interpreted.need || interpreted.use_case || submittedAdvisor.need] || 'Dina behov',
    Object.hasOwn(interpreted, 'min_tow_kg') ? interpreted.min_tow_kg > 0 ? interpreted.min_tow_kg > 1 ? `Dragvikt: minst ${interpreted.min_tow_kg} kg` : 'Dragkrok önskas' : null : /drag/i.test(submittedAdvisor.prompt) ? 'Dragkrok önskas' : null,
    Object.hasOwn(interpreted, 'awd_required') ? interpreted.awd_required ? 'Fyrhjulsdrift önskas' : null : /fyrhjul|\bawd\b/i.test(submittedAdvisor.prompt) ? 'Fyrhjulsdrift önskas' : null,
    interpreted.min_seats ? `Minst ${interpreted.min_seats} sittplatser` : null,
  ].filter(Boolean) : [];
  const dirty = submittedAdvisor && JSON.stringify(advisor) !== JSON.stringify(submittedAdvisor);
  const applySuggestion = (suggestion) => {
    setAdvisor({ ...advisor, prompt: suggestion.prompt, need: suggestion.need });
    document.getElementById('home-advisor-query')?.focus();
    document.getElementById('hitta-elbil')?.scrollIntoView({ behavior: preferredScrollBehavior(), block: 'start' });
  };
  const cardProps = { navigate, renderImage, appPath, onCompare };

  return <div className="consumerHome">
    <section className={drivingWeek ? "homeHero homeContainer homeHeroFirst" : "homeHero homeContainer"} id="hitta-elbil" aria-labelledby="home-heading">
      <div className="homeHeroCopy">
        <h1 id="home-heading">Få hjälp att välja elbil</h1>
        <p className="homeHeroIntro">{localAdvisor ? 'Beskriv dina krav. Förhandsvisningen hämtar förslag ur den sparade katalogen.' : 'Beskriv dina krav, till exempel budget, bagageutrymme eller dragkrok.'}</p>
        <form className="homeAdvisorForm" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
          <label htmlFor="home-advisor-query"><Sparkles size={17} /> Vad är viktigt för dig?</label>
          <textarea id="home-advisor-query" rows="3" value={advisor.prompt} onChange={(event) => setAdvisor({ ...advisor, prompt: event.target.value })} placeholder="Jag söker en familjebil under 600 000 kr med lång räckvidd och dragkrok..." />
          <div className="homeAdvisorFormActions">
            <button className="homeAdjust" type="button" aria-expanded={advanced} aria-controls="home-advisor-settings" onClick={() => setAdvanced(!advanced)}><SlidersHorizontal size={16} /> Anpassa <ChevronDown size={14} /></button>
            <button className="uiPrimary" type="submit" disabled={!cars.length || status.state === 'loading'}>{status.state === 'loading' ? 'Söker åt dig...' : 'Hitta min elbil'}{status.state === 'loading' ? <span className="homeSpinner" /> : <ArrowRight size={18} />}</button>
          </div>
          <div className="homeAdvisorSettings" id="home-advisor-settings" hidden={!advanced}>
            <div><label htmlFor="home-budget">Budget</label><output htmlFor="home-budget">{money(advisor.budget)}</output><input id="home-budget" type="range" min="100000" max="1200000" step="10000" value={advisor.budget} onChange={(event) => setAdvisor({ ...advisor, budget: Number(event.target.value), budgetExplicit: true })} /></div>
            <div><label htmlFor="home-range">Minsta räckvidd</label><output htmlFor="home-range">{advisor.range} km</output><input id="home-range" type="range" min="50" max="1000" step="10" value={advisor.range} onChange={(event) => setAdvisor({ ...advisor, range: Number(event.target.value), rangeExplicit: true })} /></div>
          </div>
        </form>
        <div className="homeSuggestions" aria-label="Exempel på bilbehov">{suggestions.map(({ icon: Icon, ...suggestion }, index) => drivingWeek && index === 0 ? <button type="button" className="homeWeekToggle" key={suggestion.label} aria-expanded={drivingWeek.open} aria-controls="din-korvecka" onClick={() => { weekFocusRequested.current = !weekOpen; drivingWeek.setOpen(!weekOpen); }}><Icon size={14} aria-hidden="true" />{suggestion.label}<ChevronDown size={14} aria-hidden="true" /></button> : <button type="button" key={suggestion.label} onClick={() => applySuggestion(suggestion)}><Icon size={14} />{suggestion.label}</button>)}</div>
      </div>
      {!drivingWeek && <aside className="homeSpotlight" aria-label="Upptäck en elbil">
        {spotlight ? <>
          <VehicleLink car={spotlight} navigate={navigate} appPath={appPath} className="homeSpotlightImage">{renderImage(spotlight, true)}<span>Upptäck {spotlight.brand}</span><span className="homePhotoArrow"><ArrowUpRight size={22} /></span></VehicleLink>
          <VehicleImageNotice car={spotlight} />
          <div className="homeSpotlightCaption"><div><span className="homeKicker">Bil ur katalogen</span><h2>{spotlight.brand} {spotlight.model}</h2></div><VehicleLink car={spotlight} navigate={navigate} appPath={appPath} className="homeTextLink">Utforska <ArrowRight size={16} /></VehicleLink></div>
          <dl className="homeSpotlightMetrics"><div><dt>{vehiclePriceLabel(spotlight)}</dt><dd>{spotlight.price ? money(spotlight.price) : 'Ej angivet'}</dd></div><div><dt>WLTP-räckvidd</dt><dd>{metric(spotlight.rangeVerified, 'km')}</dd></div><div><dt>DC-laddning</dt><dd>{metric(spotlight.dcVerified, 'kW')}</dd></div></dl>
        </> : <div className="homeSpotlightEmpty" role="status"><Search size={32} /><p>{dataStatus === 'loading' ? 'Hämtar elbilar...' : 'Biluppgifterna kunde inte hämtas just nu.'}</p></div>}
      </aside>}
      {drivingWeek && <div className="homeWeekPanel" id="din-korvecka" hidden={!drivingWeek.open}>
        <BiljournalWeek week={drivingWeek.week} setWeek={drivingWeek.setWeek} onApply={drivingWeek.onApply} />
        <button type="button" className="homeTextLink homeWeekAsk" onClick={() => applySuggestion(suggestions[0])}>Ställ frågan till AI-rådgivaren <ArrowRight size={16} aria-hidden="true" /></button>
      </div>}
    </section>

    {(status.state === 'loading' || result) && <section className="homeAdvisorResults homeContainer" id="dina-forslag" aria-labelledby="advisor-results-title" aria-busy={status.state === 'loading'}>
      <div className="homeSectionHeading"><div><span className="homeKicker">Ditt nästa steg</span><h2 id="advisor-results-title">{status.state === 'loading' ? 'Vi letar efter din nästa elbil.' : 'Dina rekommendationer'}</h2></div><div className="homeResultActions"><button type="button" className="homeTextLink" onClick={() => { setAdvanced(true); document.getElementById('home-advisor-query')?.focus(); document.getElementById('hitta-elbil')?.scrollIntoView({ behavior: preferredScrollBehavior(), block: 'start' }); }}><SlidersHorizontal size={16} /> Justera sökningen</button>{compare.length > 0 && <button type="button" className="homeTextLink" onClick={() => navigate('/jamfor')}>Jämför valda ({compare.length}) <ArrowRight size={17} /></button>}</div></div>
      <div className="homeRequirements"><strong>Dina önskemål</strong><div>{requirements.map((requirement) => <span key={requirement}>{requirement}</span>)}</div></div>
      <p className="homeResultStatus" role="status">{status.message}</p>
      {dirty && <p className="homeRefinementNote">Du har ändrat din sökning. Välj ”Hitta min elbil” för att uppdatera förslagen.</p>}
      {status.state !== 'loading' && <>{result?.summary && <p className="homeResultSummary">{result.summary}</p>}{interpreted.notes && <p className="homeRefinementNote">{interpreted.notes}</p>}{recommendations.length ? <div className="homeVehicleGrid">{recommendations.map(({ car, recommendation }) => <HomeVehicleCard key={car.id} {...cardProps} car={car} recommendation={recommendation} selected={compare.includes(car.id)} />)}</div> : <div className="homeEmpty"><h3>Ingen säker rekommendation just nu.</h3><p>Prova att ändra budget eller räckvidd. Uppgifter kan saknas för vissa krav.</p><button className="homeTextLink" onClick={() => document.getElementById('home-advisor-query')?.focus()}>Ändra dina önskemål <ArrowRight size={16} /></button></div>}</>}
      {status.state === 'loading' && <div className="homeVehicleGrid homeSkeletonGrid" aria-hidden="true">{[1, 2, 3].map((id) => <div className="homeSkeleton" key={id} />)}</div>}
    </section>}

    <section className={`homeExplore homeContainer${drivingWeek ? " homeExploreStart" : ""}`} aria-labelledby="explore-title">
      <div className={`homeSectionHeading${shareFeaturedNotice ? " homeFeaturedHeading" : ""}`}><div><h2 id="explore-title">Bilar ur katalogen</h2></div><a className="homeTextLink" href={appPath('/bilar')} onClick={(event) => { if (!event.metaKey && !event.ctrlKey) { event.preventDefault(); navigate('/bilar'); } }}>Alla elbilar <ArrowRight size={17} /></a>{shareFeaturedNotice && <div className="homeFeaturedImageContext"><p id={featuredNoticeId} className="homeFeaturedImageNotice">Pressbilder. Utrustning kan skilja mellan versioner.</p><a className="homeImageCreditLink" href={appPath('/kallor?post=bilder')} onClick={(event) => { if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && event.button === 0) { event.preventDefault(); navigate('/kallor?post=bilder'); } }}>Bildkrediter</a></div>}</div>
      {cars.length ? <div className="homeVehicleGrid">{featured.map((car) => <HomeVehicleCard key={car.id} {...cardProps} car={car} selected={compare.includes(car.id)} sharedImageNoticeId={shareFeaturedNotice ? featuredNoticeId : undefined} showPhotoHighlight={!drivingWeek} />)}</div> : <p role="status">{dataStatus === 'loading' ? 'Hämtar bilar...' : 'Biluppgifterna är tillfälligt otillgängliga. Försök igen om en stund.'}</p>}
    </section>

    <section className="homeNeedsBand"><div className="homeContainer"><div className="homeSectionHeading"><div><h2>Hitta bilar efter behov</h2></div></div><div className="homeNeedsGrid">{categories.map(({ icon: Icon, ...category }) => {
      const Tag = category.path ? 'a' : 'button';
      return <Tag key={category.title} href={category.path ? appPath(category.path) : undefined} type={category.path ? undefined : 'button'} onClick={(event) => {
        if (category.path) { if (!event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) { event.preventDefault(); navigate(category.path); } }
        else applySuggestion(category.prompt);
      }}><Icon size={24} strokeWidth={1.5} /><strong>{category.title}</strong><span>{category.text}</span><ArrowUpRight size={17} className="homeNeedArrow" /></Tag>;
    })}</div></div></section>

    {newsPreview}

    <section className="homeHow homeContainer" aria-labelledby="home-how-title"><div className="homeSectionHeading"><div><span className="homeKicker">Varför Elbilsagenten?</span><h2 id="home-how-title">Ett enklare sätt att välja elbil.</h2></div></div><ol>{[
      ['Beskriv dina behov.', 'Vardagsresor, semesterpackning eller en viss budget. Börja med det som spelar roll för dig.'],
      ['Få personliga förslag.', 'Se vilka elbilar som passar dina önskemål, med styrkor och kompromisser sida vid sida.'],
      ['Jämför och välj.', 'Titta närmare på detaljerna och jämför dina favoriter innan du tar nästa steg.'],
    ].map(([title, text], index) => <li key={title}><span className="homeStepNumber">0{index + 1}</span><h3>{title}</h3><p>{text}</p></li>)}</ol></section>
  </div>;
}
