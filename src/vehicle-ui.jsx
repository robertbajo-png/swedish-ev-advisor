import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, ArrowUpRight, BadgeCheck, Check, GitCompareArrows, LayoutGrid, List, Package, PlugZap, Plus, Route, Search, SlidersHorizontal, Weight, X } from 'lucide-react';

export const vehicleMoney = (value) => new Intl.NumberFormat('sv-SE').format(value) + ' kr';
export const vehicleMetric = (value, unit = '') => value == null ? 'Uppgift saknas' : `${value}${unit ? ` ${unit}` : ''}`;
const validDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value || '');

export function vehicleIdentity(car) {
  const canonical = car.canonicalModel || car.model;
  if (car.model.toLowerCase().startsWith(canonical.toLowerCase())) {
    return { model: car.model.slice(0, canonical.length), variant: car.model.slice(canonical.length).trim() };
  }
  return { model: car.model, variant: '' };
}

export function VehicleLink({ car, navigate, children, className, appPath }) {
  const path = `/bilar/${car.id}`;
  return <a className={className} href={appPath(path)} onClick={(event) => {
    if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate(path); }
  }}>{children}</a>;
}

export function VehicleCard({ car, selected, onCompare, navigate, renderImage, appPath, recommendation, className = '', compareLimitReached = false }) {
  const identity = vehicleIdentity(car);
  const priceType = car.priceType === 'campaign_price' ? 'Kampanjpris' : car.priceType === 'dealer_offer' ? 'Återförsäljarerbjudande' : 'Pris från';
  const highlight = car.rangeVerified >= 650 ? `${car.rangeVerified} km WLTP` : car.towingVerified >= 2000 ? `${car.towingVerified} kg dragvikt` : null;
  return <article className={`vehicleCard homeVehicleCard ${className}`}>
    <VehicleLink car={car} navigate={navigate} appPath={appPath} className="homeVehiclePhoto">{renderImage(car)}{highlight && <span className="vehiclePhotoLabel">{highlight}</span>}</VehicleLink>
    <div className="homeVehicleBody">
      <h3><VehicleLink car={car} navigate={navigate} appPath={appPath}>{car.brand} {identity.model}</VehicleLink></h3>
      <p className="vehicleVariant">{identity.variant || 'Modelluppgifter'}</p>
      <p className="homeVehiclePrice">{car.price ? <>{vehicleMoney(car.price)}<span>{priceType}{car.priceType === 'campaign_price' && validDate(car.priceValidUntil) ? ` · gäller till ${car.priceValidUntil}` : ''}</span></> : <>Pris ej angivet<span>Svenskt pris saknas i underlaget</span></>}</p>
      <dl className="homeVehicleSpecs">
        {[['WLTP', car.rangeVerified, 'km', Route], ['DC-laddning', car.dcVerified, 'kW', PlugZap], ['Dragvikt', car.towingVerified, 'kg', Weight], ['Bagage', car.cargoVerified, 'l', Package]].map(([label, value, unit, Icon]) => <div key={label}><dt><Icon size={15} aria-hidden="true" />{label}</dt><dd>{vehicleMetric(value, unit)}</dd></div>)}
      </dl>
      {recommendation && <div className="homeVehicleReason"><h4>Varför den passar</h4><ul>{recommendation.reasons?.slice(0, 2).map((reason) => <li key={reason}><Check size={15} />{reason}</li>)}</ul>{!!recommendation.tradeoffs?.length && <><h4>Att tänka på</h4><p>{recommendation.tradeoffs.slice(0, 2).join(' ')}</p></>}</div>}
      <div className="vehicleSourceLine"><a href={car.source} target="_blank" rel="noreferrer"><BadgeCheck size={13} /> Bilens källa <ArrowUpRight size={12} /></a>{validDate(car.verifiedAt) && <time dateTime={car.verifiedAt}>{car.verifiedAt}</time>}</div>
      <div className="homeVehicleActions"><VehicleLink car={car} navigate={navigate} appPath={appPath}>Visa detaljer <ArrowUpRight size={16} /></VehicleLink><button type="button" aria-pressed={selected} onClick={() => onCompare(car.id)} title={selected ? 'Ta bort ur jämförelse' : compareLimitReached ? 'Ersätter äldsta valet i jämförelsen' : 'Lägg till i jämförelse'}>{selected ? <Check size={16} /> : <GitCompareArrows size={16} />}{selected ? 'Vald' : 'Jämför'}</button></div>
    </div>
  </article>;
}

export function VehicleCatalog({ cars, ranked, filters, setFilters, resetFilters, dataStatus, segment, renderFilters, renderCard, onCompare, compare, navigate, appPath }) {
  const [view, setView] = useState('grid');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const dialog = useRef(null);
  const filterTrigger = useRef(null);
  useEffect(() => {
    if (!drawerOpen) return;
    dialog.current?.showModal();
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, [drawerOpen]);
  const closeDrawer = () => { dialog.current?.close(); setDrawerOpen(false); filterTrigger.current?.focus(); };
  const brands = [...new Set(cars.map((car) => car.brand))].sort();
  return <section className="vehicleCatalog vehicleContainer" id="cars" aria-labelledby="catalog-title">
    <div className="vehiclePageIntro"><span className="vehicleEyebrow">Elbilsguiden / {segment ? 'Dina behov' : 'Alla elbilar'}</span><h1 id="catalog-title">{segment?.title || 'Hitta din nästa elbil.'}</h1><p>{segment?.description || 'Upptäck modellerna, jämför detaljerna och hitta det som passar din vardag.'}</p></div>
    <div className="catalogLayout">
      <div className="catalogFiltersDesktop">{renderFilters('desktop', brands)}</div>
      <div className="catalogResults">
        <div className="catalogToolbar">
          <div className="catalogResultCount" role="status"><strong>{ranked.length}</strong> {ranked.length === 1 ? 'variant' : 'varianter'}</div>
          <button ref={filterTrigger} type="button" className="catalogFilterTrigger" onClick={() => setDrawerOpen(true)}><SlidersHorizontal size={16} /> Filter</button>
          <label className="catalogSort"><span>Sortera</span><select aria-label="Sortera bilar" value={filters.sort} onChange={(event) => setFilters({ ...filters, sort: event.target.value })}><option value="match">Smart matchning</option><option value="price">Lägst pris</option><option value="range">Längst räckvidd</option><option value="efficiency">Lägst förbrukning</option></select></label>
          <div className="catalogViewToggle" role="group" aria-label="Visningsläge"><button type="button" aria-pressed={view === 'grid'} title="Kortvy" aria-label="Kortvy" onClick={() => setView('grid')}><LayoutGrid size={17} /></button><button type="button" aria-pressed={view === 'table'} title="Tabellvy" aria-label="Tabellvy" onClick={() => setView('table')}><List size={18} /></button></div>
        </div>
        <label className="catalogSearch"><Search size={18} /><input aria-label="Sök bilmodell" type="search" value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} placeholder="Sök på märke, modell eller variant" /></label>
        {dataStatus === 'loading' ? <div className="catalogLoading" role="status">Hämtar elbilar...</div> : ranked.length === 0 ? <div className="vehicleEmpty"><Search size={28} /><h2>{dataStatus === 'error' ? 'Biluppgifterna kunde inte hämtas.' : 'Ingen bil matchar just nu.'}</h2><p>{dataStatus === 'error' ? 'Försök igen om en stund.' : 'Prova en annan budget, räckvidd eller sökning.'}</p><button type="button" className="uiPrimary" onClick={resetFilters}>Återställ filter</button></div> : view === 'grid' ? <div className="carGrid vehicleCardGrid">{ranked.map(renderCard)}</div> : <div className="vehicleTableScroll" tabIndex={0} aria-label="Bilöversikt, rulla i sidled"><table className="catalogTable"><caption className="srOnly">Elbilar som matchar dina filter</caption><thead><tr>{['Bil', 'Pris', 'WLTP', 'DC-laddning', 'Dragvikt', 'Jämför'].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{ranked.map((car) => <tr key={car.id}><th scope="row"><VehicleLink car={car} navigate={navigate} appPath={appPath}>{car.brand} {car.model}<ArrowUpRight size={14} /></VehicleLink></th><td>{car.price ? vehicleMoney(car.price) : 'Ej angivet'}{car.priceType && car.priceType !== 'list_price' && <small>{car.priceType === 'campaign_price' ? 'Kampanjpris' : 'Återförsäljarerbjudande'}</small>}</td><td>{vehicleMetric(car.rangeVerified, 'km')}</td><td>{vehicleMetric(car.dcVerified, 'kW')}</td><td>{vehicleMetric(car.towingVerified, 'kg')}</td><td><button aria-label={`Jämför ${car.brand} ${car.model}`} aria-pressed={compare.includes(car.id)} onClick={() => onCompare(car.id)}>{compare.includes(car.id) ? <Check size={18} /> : <Plus size={18} />}</button></td></tr>)}</tbody></table></div>}
      </div>
    </div>
    {drawerOpen && <dialog ref={dialog} className="catalogFilterDialog" aria-labelledby="mobile-filter-title" onCancel={(event) => { event.preventDefault(); closeDrawer(); }} onClose={() => { setDrawerOpen(false); filterTrigger.current?.focus(); }}><div className="catalogDialogHeading"><h2 id="mobile-filter-title">Anpassa urvalet</h2><button type="button" aria-label="Stäng filter" onClick={closeDrawer}><X size={22} /></button></div>{renderFilters('mobile', brands)}<button className="uiPrimary" type="button" onClick={closeDrawer}>Visa {ranked.length} varianter <ArrowRight size={17} /></button></dialog>}
  </section>;
}

export function ComparisonSelection({ cars, allCars, onCompare, renderImage, navigate, appPath }) {
  return <div className="comparisonSelection" aria-label="Valda bilar">
    {cars.map((car) => <article className="comparisonVehicle" key={car.id}><div className="comparisonVehiclePhoto">{renderImage(car)}<button type="button" aria-label={`Ta bort ${car.brand} ${car.model}`} onClick={() => onCompare(car.id)}><X size={17} /></button></div><div><span>{car.brand}</span><h2><VehicleLink car={car} navigate={navigate} appPath={appPath}>{car.model}</VehicleLink></h2><p>{car.price ? vehicleMoney(car.price) : 'Pris ej angivet'}</p>{car.priceType && car.priceType !== 'list_price' && <small>{car.priceType === 'campaign_price' ? 'Kampanjpris' : 'Återförsäljarerbjudande'}</small>}</div></article>)}
    {cars.length < 3 && <div className="comparisonAdd"><Plus size={26} /><strong>{cars.length ? 'Ett alternativ till?' : 'Vilka bilar väljer du mellan?'}</strong><label htmlFor="comparison-add-car">Lägg till en bil</label><select id="comparison-add-car" value="" onChange={(event) => event.target.value && onCompare(event.target.value)}><option value="">Välj modell och variant</option>{allCars.filter((car) => !cars.some((item) => item.id === car.id)).map((car) => <option key={car.id} value={car.id}>{car.brand} {car.model}</option>)}</select><a className="homeTextLink" href={appPath('/bilar')} onClick={(event) => { if (!event.ctrlKey && !event.metaKey) { event.preventDefault(); navigate('/bilar'); } }}>Utforska alla elbilar <ArrowRight size={16} /></a></div>}
  </div>;
}
