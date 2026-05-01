import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  ArrowRight,
  BadgeCheck,
  Bot,
  CarFront,
  Check,
  ChevronRight,
  ExternalLink,
  Gauge,
  HeartHandshake,
  Home,
  MountainSnow,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trees,
  Users,
  Zap
} from 'lucide-react';
import './styles.css';

const fallbackCars = [
  {
    id: 'tesla-model-y-lr-rwd',
    brand: 'Tesla',
    model: 'Model Y Long Range RWD',
    body: 'SUV',
    seats: 5,
    price: 579170,
    range: 657,
    consumption: 12.7,
    dc: 250,
    cargo: 2118,
    towing: 1600,
    drivetrain: 'Bakhjulsdrift',
    familyScore: 94,
    winterScore: 84,
    commuteScore: 96,
    source: 'https://www.tesla.com/sv_SE/modely',
    verifiedAt: '2026-04-30',
    image:
      'https://images.unsplash.com/photo-1560958089-b8a1929cea89?auto=format&fit=crop&w=1400&q=82',
    summary:
      'Rymlig, effektiv och ovanligt stark på långresor. Passar familjer som vill ha maximal räckvidd per krona.'
  },
  {
    id: 'tesla-model-y-performance',
    brand: 'Tesla',
    model: 'Model Y Performance',
    body: 'SUV',
    seats: 5,
    price: 719170,
    range: 580,
    consumption: 16.2,
    dc: 250,
    cargo: 2138,
    towing: 1600,
    drivetrain: 'Fyrhjulsdrift',
    familyScore: 88,
    winterScore: 92,
    commuteScore: 87,
    source: 'https://www.tesla.com/sv_SE/modely',
    verifiedAt: '2026-04-30',
    image:
      'https://images.unsplash.com/photo-1617788138017-80ad40651399?auto=format&fit=crop&w=1400&q=82',
    summary:
      'Snabb familje-SUV med mycket plats och trygg vinterkänsla. För dig som prioriterar kraft och grepp.'
  },
  {
    id: 'volvo-ex30-extended',
    brand: 'Volvo',
    model: 'EX30 Extended Range',
    body: 'Kompakt SUV',
    seats: 5,
    price: 429000,
    range: 476,
    consumption: 17.0,
    dc: 153,
    cargo: 318,
    towing: 1600,
    drivetrain: 'Bakhjulsdrift',
    familyScore: 70,
    winterScore: 82,
    commuteScore: 91,
    source: 'https://www.volvocars.com/se/cars/ex30-electric/',
    verifiedAt: '2026-04-28',
    image:
      'https://images.unsplash.com/photo-1619767886558-efdc259cde1a?auto=format&fit=crop&w=1400&q=82',
    summary:
      'Kompakt, snabb och lätt att leva med i stan. Ett premiumval för pendling och helgresor.'
  },
  {
    id: 'kia-ev3-long-range',
    brand: 'Kia',
    model: 'EV3 Long Range',
    body: 'Kompakt SUV',
    seats: 5,
    price: 489900,
    range: 605,
    consumption: 15.9,
    dc: 128,
    cargo: 460,
    towing: 1000,
    drivetrain: 'Framhjulsdrift',
    familyScore: 86,
    winterScore: 78,
    commuteScore: 93,
    source: 'https://www.kia.com/se/nya-bilar/ev3/upptack/',
    verifiedAt: '2026-04-29',
    image:
      'https://images.unsplash.com/photo-1593941707882-a5bba14938c7?auto=format&fit=crop&w=1400&q=82',
    summary:
      'Lång räckvidd i ett smidigt format med praktisk vardagskänsla. Väldigt stark totalekonomi.'
  },
  {
    id: 'polestar-2-lr-sm',
    brand: 'Polestar',
    model: '2 Long Range Single Motor',
    body: 'Fastback',
    seats: 5,
    price: 599000,
    range: 659,
    consumption: 14.8,
    dc: 205,
    cargo: 405,
    towing: 1500,
    drivetrain: 'Bakhjulsdrift',
    familyScore: 78,
    winterScore: 83,
    commuteScore: 94,
    source: 'https://www.polestar.com/se/polestar-2/specifications/',
    verifiedAt: '2026-04-30',
    image:
      'https://images.unsplash.com/photo-1617654112368-307921291f42?auto=format&fit=crop&w=1400&q=82',
    summary:
      'Lång räckvidd, snabb laddning och skandinavisk förarkänsla. Passar dig som kör mycket.'
  },
  {
    id: 'polestar-2-lr-dm',
    brand: 'Polestar',
    model: '2 Long Range Dual Motor',
    body: 'Fastback',
    seats: 5,
    price: 639000,
    range: 596,
    consumption: 15.8,
    dc: 205,
    cargo: 405,
    towing: 1500,
    drivetrain: 'Fyrhjulsdrift',
    familyScore: 77,
    winterScore: 91,
    commuteScore: 89,
    source: 'https://www.polestar.com/se/polestar-2/specifications/',
    verifiedAt: '2026-04-30',
    image:
      'https://images.unsplash.com/photo-1591293835940-934a7c4f2d9b?auto=format&fit=crop&w=1400&q=82',
    summary:
      'Trygg fyrhjulsdrift och premiumkänsla utan att tappa långresestyrka. Byggd för nordiskt väder.'
  }
];

const needs = [
  { id: 'familj', title: 'Familj & vardag', text: 'Barnstol, matkassar, fjällpackning och lugn ekonomi.', icon: Users },
  { id: 'pendling', title: 'Pendling', text: 'Låg förbrukning, snabb laddning och enkel parkering.', icon: Trees },
  { id: 'vinter', title: 'Vinter & fritid', text: 'Grepp, dragvikt och räckvidd när temperaturen faller.', icon: MountainSnow }
];

const formatSEK = (value) =>
  new Intl.NumberFormat('sv-SE', { style: 'currency', currency: 'SEK', maximumFractionDigits: 0 }).format(value);

const carImages = [
  'https://images.unsplash.com/photo-1560958089-b8a1929cea89?auto=format&fit=crop&w=1400&q=82',
  'https://images.unsplash.com/photo-1617788138017-80ad40651399?auto=format&fit=crop&w=1400&q=82',
  'https://images.unsplash.com/photo-1619767886558-efdc259cde1a?auto=format&fit=crop&w=1400&q=82',
  'https://images.unsplash.com/photo-1593941707882-a5bba14938c7?auto=format&fit=crop&w=1400&q=82'
];

function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

function transformPublicVariant(row, index) {
  const brand = row.brand;
  const model = `${row.model} ${row.variant_name || ''}`.trim();
  return {
    id: `${slug(brand)}-${slug(model)}`,
    brand,
    model,
    body: row.body_type || 'Elbil',
    seats: row.seats || 5,
    price: row.price_sek || null,
    range: row.wltp_range_km || 0,
    consumption: 16,
    dc: row.dc_charge_kw || 0,
    cargo: row.boot_liters || 0,
    towing: row.tow_kg || 0,
    drivetrain: row.drivetrain || 'Ej verifierad',
    familyScore: row.boot_liters ? Math.min(98, 55 + row.boot_liters / 12) : 68,
    winterScore: row.drivetrain?.toLowerCase().includes('fyr') ? 92 : 76,
    commuteScore: row.wltp_range_km ? Math.min(98, 55 + row.wltp_range_km / 12) : 70,
    source: row.source_url,
    verifiedAt: row.verified_at?.slice(0, 10) || 'Verifierad källa',
    image: carImages[index % carImages.length],
    marketSeen: row.market_seen,
    availableConfirmed: row.available_confirmed,
    discontinuedCandidate: row.discontinued_candidate,
    comingOrLowVolume: row.coming_or_low_volume,
    summary:
      row.source_quote ||
      'Publicerad från canonical EV-databasen med Mobility Sweden som marknadsindex och officiell källa för specifikationer.'
  };
}

async function loadPublicCars() {
  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !anonKey) return null;
  const response = await fetch(`${supabaseUrl.replace(/\/$/, '')}/rest/v1/public_ev_variants?select=*`, {
    headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` }
  });
  if (!response.ok) throw new Error(`Supabase public view fetch failed: ${response.status}`);
  const rows = await response.json();
  return rows.map(transformPublicVariant);
}

function scoreCar(car, advisor) {
  const text = advisor.prompt.toLowerCase();
  const price = car.price || 9999999;
  const range = car.range || 0;
  const budgetFit = price <= advisor.budget ? 30 : Math.max(0, 30 - (price - advisor.budget) / 11000);
  const rangeFit = Math.min(22, (range / advisor.range) * 22);
  const needFit =
    advisor.need === 'familj'
      ? car.familyScore / 4
      : advisor.need === 'vinter'
        ? car.winterScore / 4
        : car.commuteScore / 4;
  const textFit =
    (text.includes('drag') && car.towing >= 1500 ? 8 : 0) +
    (text.includes('barn') && car.cargo > 450 ? 6 : 0) +
    (text.includes('billig') && car.price < 500000 ? 7 : 0) +
    (text.includes('vinter') && car.drivetrain === 'Fyrhjulsdrift' ? 8 : 0);
  return Math.round(Math.min(100, budgetFit + rangeFit + needFit + textFit));
}

function reasonsFor(car, advisor) {
  const reasons = [];
  if (car.range >= advisor.range) reasons.push(`${car.range} km WLTP mot ditt mål på ${advisor.range} km`);
  if (car.price && car.price <= advisor.budget) reasons.push(`pris från ${formatSEK(car.price)} inom vald budget`);
  if (car.towing >= 1500) reasons.push(`dragvikt upp till ${car.towing} kg`);
  if (advisor.need === 'vinter' && car.drivetrain === 'Fyrhjulsdrift') reasons.push('fyrhjulsdrift för vintervägar');
  if (advisor.need === 'familj' && car.cargo > 450) reasons.push(`${car.cargo} liter lastutrymme`);
  return reasons.slice(0, 3);
}

function App() {
  const [cars, setCars] = useState(fallbackCars);
  const [dataNotice, setDataNotice] = useState('Visar lokal fallbackdata tills Supabase public views är konfigurerade.');
  const [advisor, setAdvisor] = useState({
    prompt: 'Vi är en familj i Stockholm med två barn, kör till fjällen ibland och vill ha dragkrok.',
    budget: 620000,
    range: 520,
    need: 'familj'
  });
  const [filters, setFilters] = useState({ body: 'Alla', maxPrice: 750000, sort: 'match' });
  const [compare, setCompare] = useState(['tesla-model-y-lr-rwd', 'kia-ev3-long-range', 'polestar-2-lr-sm']);

  useEffect(() => {
    loadPublicCars()
      .then((publicCars) => {
        if (!publicCars?.length) return;
        setCars(publicCars);
        setCompare(publicCars.slice(0, 3).map((car) => car.id));
        setDataNotice('Visar publicerade elbilar från Supabase public views.');
      })
      .catch((error) => {
        setDataNotice(`Visar lokal fallbackdata. ${error.message}`);
      });
  }, []);

  const ranked = useMemo(() => {
    return cars
      .map((car) => ({ ...car, score: scoreCar(car, advisor), reasons: reasonsFor(car, advisor) }))
      .filter((car) => filters.body === 'Alla' || car.body === filters.body)
      .filter((car) => !car.price || car.price <= filters.maxPrice)
      .sort((a, b) => {
        if (filters.sort === 'price') return (a.price || 9999999) - (b.price || 9999999);
        if (filters.sort === 'range') return b.range - a.range;
        if (filters.sort === 'efficiency') return a.consumption - b.consumption;
        return b.score - a.score;
      });
  }, [advisor, filters]);

  const compareCars = compare.map((id) => cars.find((car) => car.id === id)).filter(Boolean);
  const topCar = ranked[0] ?? cars[0];

  function toggleCompare(id) {
    setCompare((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      return [...current.slice(-2), id];
    });
  }

  return (
    <main>
      <header className="siteHeader">
        <a className="brand" href="#home">
          <span className="brandMark"><Zap size={18} /></span>
          <span>Elbilsguiden</span>
        </a>
        <nav>
          <a href="#cars">Bilar</a>
          <a href="#compare">Jämför</a>
          <a href="#quality">Verifiering</a>
        </nav>
      </header>

      <HeroSearch advisor={advisor} setAdvisor={setAdvisor} shortlist={ranked.slice(0, 3)} />

      <section className="needSection">
        <div className="sectionIntro">
          <span className="eyebrow">Så fungerar det</span>
          <h2>Från behov till trygg shortlist.</h2>
        </div>
        <div className="needGrid">
          {needs.map((need) => (
            <NeedCategoryCard
              key={need.id}
              need={need}
              active={advisor.need === need.id}
              onClick={() => setAdvisor({ ...advisor, need: need.id })}
            />
          ))}
        </div>
      </section>

      <AiAdvisorPanel />

      <section className="carsSection" id="cars">
        <div className="sectionIntro wide">
          <span className="eyebrow">/cars</span>
          <h2>Utforska verifierade elbilar i Sverige.</h2>
          <p>Kort först, tabell sen. Filtrera på det som faktiskt påverkar vardagen.</p>
          <p className="dataNotice">{dataNotice}</p>
        </div>
        <div className="carsLayout">
          <FilterSidebar filters={filters} setFilters={setFilters} />
          <div className="carGrid">
            {ranked.map((car) => (
              <CarCard
                key={car.id}
                car={car}
                selected={compare.includes(car.id)}
                onCompare={() => toggleCompare(car.id)}
              />
            ))}
          </div>
        </div>
      </section>

      <CompareBar cars={compareCars} />

      <section className="compareSection" id="compare">
        <div className="decisionReport">
          <div>
            <span className="eyebrow">/compare</span>
            <h2>Beslutsrapport</h2>
            <p>
              AI-sammanfattningen väger räckvidd, budget, laddning, lastutrymme och nordiska behov
              mot varandra innan tabellen visar detaljerna.
            </p>
          </div>
          <div className="reportCard">
            <Sparkles size={22} />
            <h3>Rekommendation</h3>
            <p>
              {compareCars[0]?.brand} {compareCars[0]?.model} är starkast som helhetsval. Välj
              {` ${compareCars[1]?.brand} ${compareCars[1]?.model} om pris och kompakt format väger tyngre, `}
              och {compareCars[2]?.brand} {compareCars[2]?.model} om premiumkänsla och lång räckvidd är viktigast.
            </p>
          </div>
        </div>
        <ComparisonTable cars={compareCars} />
      </section>

      <section className="qualitySection" id="quality">
        <div className="sectionIntro wide">
          <span className="eyebrow">Verifierad data</span>
          <h2>Marknadsdata först, specifikationer från källan.</h2>
          <p>
            Mobility Sweden används för att se vilka elbilsmodeller som faktiskt registreras i Sverige.
            Priser, versioner och tekniska värden hämtas därefter från officiella svenska tillverkar-
            eller importörskällor innan något visas publikt.
          </p>
        </div>
        <div className="qualityGrid">
          <QualityStep title="1. Marknadsindex" text="Mobility Sweden identifierar elbilar med svensk registreringsaktivitet." />
          <QualityStep title="2. Primärkällor" text="Officiella tillverkar- och importörssidor används för pris och specifikationer." />
          <QualityStep title="3. Validerad publicering" text="AI-extraktion blir aldrig publik förrän regler och granskning godkänt datan." />
        </div>
      </section>

      <footer>
        <span><ShieldCheck size={16} /> Oberoende beslutsstöd med verifierade källor.</span>
        <a href="#home"><Home size={16} /> Till toppen</a>
      </footer>
    </main>
  );
}

function HeroSearch({ advisor, setAdvisor, shortlist }) {
  const topCar = shortlist[0] ?? fallbackCars[0];
  const requirementChips = [
    `Max ${formatSEK(advisor.budget)}`,
    `Minst ${advisor.range} km`,
    needs.find((need) => need.id === advisor.need)?.title ?? 'Valda behov',
    advisor.prompt.toLowerCase().includes('drag') ? 'Dragkrok' : 'Källgranskat'
  ];

  return (
    <section className="heroSearch" id="home">
      <div className="heroCopy">
        <VerificationBadge />
        <h1>Hitta rätt elbil i Sverige med AI.</h1>
        <p>Beskriv budget, körning och behov – få en shortlist med verifierade elbilar, tydliga kompromisser och källor.</p>
      </div>
      <div className="heroSearchBox">
        <label htmlFor="needSearch">AI-rådgivare</label>
        <div className="promptBox">
          <Search size={20} />
          <textarea
            id="needSearch"
            value={advisor.prompt}
            onChange={(event) => setAdvisor({ ...advisor, prompt: event.target.value })}
            rows="4"
          />
        </div>
        <div className="heroControls">
          <label>
            Budget
              <input
                type="range"
                min="350000"
                max="1200000"
                step="10000"
                value={advisor.budget}
                onChange={(event) => setAdvisor({ ...advisor, budget: Number(event.target.value) })}
            />
            <strong>{formatSEK(advisor.budget)}</strong>
          </label>
          <label>
            Minsta räckvidd
              <input
                type="range"
                min="300"
                max="1000"
                step="10"
                value={advisor.range}
                onChange={(event) => setAdvisor({ ...advisor, range: Number(event.target.value) })}
              />
            <strong>{advisor.range} km</strong>
          </label>
        </div>
        <a className="primaryCta" href="#cars">
          Visa rekommenderade bilar <ArrowRight size={18} />
        </a>
        <div className="mockResponse">
          <div>
            <h3>Tolkade krav</h3>
            <div className="requirementChips">
              {requirementChips.map((chip) => <span key={chip}>{chip}</span>)}
            </div>
          </div>
          <div>
            <h3>Preliminär shortlist</h3>
            <ol>
              {(shortlist.length ? shortlist : [fallbackCars[0]]).map((car) => (
                <li key={car.id}>
                  <strong>{car.brand} {car.model}</strong>
                  <span>{car.reasons[0] ?? 'Stark totalmatchning med verifierade uppgifter'}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
      <aside className="heroRecommendation">
        <span>Bästa match just nu</span>
        <img src={topCar.image} alt={`${topCar.brand} ${topCar.model}`} />
        <h2>{topCar.brand} {topCar.model}</h2>
        <p>{topCar.summary}</p>
      </aside>
    </section>
  );
}

function AiAdvisorPanel() {
  return (
    <section className="advisorPanel">
      <ConsumerStep title="Beskriv dina behov" text="Skriv fritt om budget, familj, pendling, resor, dragkrok och laddning." />
      <ConsumerStep title="Få en shortlist" text="Rådgivaren väljer ut 2–3 relevanta bilar och förklarar kompromisserna." />
      <ConsumerStep title="Jämför med källor" text="Se pris, räckvidd, laddning, bagage och verifieringsdatum innan du går vidare." />
    </section>
  );
}

function NeedCategoryCard({ need, active, onClick }) {
  const Icon = need.icon;
  return (
    <button className={`needCard ${active ? 'active' : ''}`} onClick={onClick}>
      <span><Icon size={22} /></span>
      <h3>{need.title}</h3>
      <p>{need.text}</p>
    </button>
  );
}

function FilterSidebar({ filters, setFilters }) {
  return (
    <aside className="filterSidebar">
      <div className="filterTitle"><SlidersHorizontal size={18} /> Filter</div>
      <label>
        Kaross
        <select value={filters.body} onChange={(event) => setFilters({ ...filters, body: event.target.value })}>
          <option>Alla</option>
          <option>SUV</option>
          <option>Kompakt SUV</option>
          <option>Fastback</option>
        </select>
      </label>
      <label>
        Maxpris
        <input
          type="range"
          min="420000"
          max="1200000"
          step="10000"
          value={filters.maxPrice}
          onChange={(event) => setFilters({ ...filters, maxPrice: Number(event.target.value) })}
        />
        <strong>{formatSEK(filters.maxPrice)}</strong>
      </label>
      <label>
        Sortera
        <select value={filters.sort} onChange={(event) => setFilters({ ...filters, sort: event.target.value })}>
          <option value="match">AI-matchning</option>
          <option value="price">Lägst pris</option>
          <option value="range">Längst räckvidd</option>
          <option value="efficiency">Lägst förbrukning</option>
        </select>
      </label>
    </aside>
  );
}

function CarCard({ car, selected, onCompare }) {
  return (
    <article className="carCard">
      <div className="carImageWrap">
        <img src={car.image} alt={`${car.brand} ${car.model}`} />
        <div className="matchBadge">{car.score}% match</div>
      </div>
      <div className="carContent">
        <div className="carTopline">
          <span>{car.body}</span>
          <VerificationBadge compact date={car.verifiedAt} />
        </div>
        <h3>{car.brand} {car.model}</h3>
        <p>{car.summary}</p>
        <div className="metricGrid">
          <Metric label="Pris från" value={car.price ? formatSEK(car.price) : 'Ej angivet'} />
          <Metric label="WLTP" value={`${car.range} km`} />
          <Metric label="DC" value={`${car.dc} kW`} />
          <Metric label="Dragvikt" value={`${car.towing} kg`} />
          <Metric label="Bagage" value={`${car.cargo} l`} />
          <Metric label="Verifierad" value={car.verifiedAt} />
        </div>
        <ul>
          {car.reasons.map((reason) => (
            <li key={reason}><Check size={15} /> {reason}</li>
          ))}
        </ul>
        <div className="cardActions">
          <a href={car.source} target="_blank" rel="noreferrer">
            Visa detaljer <ExternalLink size={15} />
          </a>
          <button onClick={onCompare}>{selected ? 'Vald' : 'Jämför'} <ChevronRight size={15} /></button>
        </div>
      </div>
    </article>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metricItem">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CompareBar({ cars }) {
  return (
    <div className="compareBar">
      <span>{cars.length} valda för jämförelse</span>
      <div>
        {cars.map((car) => <strong key={car.id}>{car.brand} {car.model}</strong>)}
      </div>
      <a href="#compare">Öppna rapport <ArrowRight size={16} /></a>
    </div>
  );
}

function ComparisonTable({ cars }) {
  const rows = [
    ['Pris från', (car) => formatSEK(car.price)],
    ['WLTP-räckvidd', (car) => `${car.range} km`],
    ['Snabbladdning', (car) => `${car.dc} kW`],
    ['Bagage', (car) => `${car.cargo} liter`],
    ['Dragvikt', (car) => `${car.towing} kg`],
    ['Drivlina', (car) => car.drivetrain]
  ];

  return (
    <div className="comparisonTable" role="table" aria-label="Jämförelse av elbilar">
      <div className="tableRow tableHead">
        <span>Mått</span>
        {cars.map((car) => <strong key={car.id}>{car.brand} {car.model}</strong>)}
      </div>
      {rows.map(([label, getter]) => (
        <div className="tableRow" key={label}>
          <span>{label}</span>
          {cars.map((car) => <strong key={`${car.id}-${label}`}>{getter(car)}</strong>)}
        </div>
      ))}
    </div>
  );
}

function VerificationBadge({ compact = false, date }) {
  return (
    <span className={`verificationBadge ${compact ? 'compact' : ''}`}>
      <BadgeCheck size={compact ? 14 : 16} />
      {compact ? date : 'Verifierade svenska källor'}
    </span>
  );
}

function ConsumerStep({ title, text }) {
  return (
    <article>
      <Bot size={20} />
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}

function QualityStep({ title, text }) {
  return (
    <article>
      <HeartHandshake size={22} />
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}

createRoot(document.getElementById('root')).render(<App />);
