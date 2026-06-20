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
  Package,
  PlugZap,
  Route,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Tag,
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
    image: null,
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
    image: null,
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
    image: null,
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
    image: null,
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
    image: null,
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
    image: null,
    summary:
      'Trygg fyrhjulsdrift och premiumkänsla utan att tappa långresestyrka. Byggd för nordiskt väder.'
  }
];

const needs = [
  { id: 'familj', title: 'Familj & vardag', text: 'Barnstol, matkassar, fjällpackning och lugn ekonomi.', icon: Users },
  { id: 'pendling', title: 'Pendling', text: 'Låg förbrukning, snabb laddning och enkel parkering.', icon: Gauge },
  { id: 'vinter', title: 'Vinter & fritid', text: 'Grepp, dragvikt och räckvidd när temperaturen faller.', icon: MountainSnow }
];

const formatSEK = (value) =>
  new Intl.NumberFormat('sv-SE', { style: 'currency', currency: 'SEK', maximumFractionDigits: 0 }).format(value);

function detailValue(value, unit = '') {
  if (value === null || value === undefined || value === '') return 'Uppgift saknas';
  return `${value}${unit ? ` ${unit}` : ''}`;
}

function splitCarTitle(car) {
  const modelWithoutBrand = car.model.replace(new RegExp(`^${car.brand}\\s+`, 'i'), '').trim();
  const tokens = modelWithoutBrand.split(/\s+/).filter(Boolean);
  if (tokens.length <= 2) return { title: `${car.brand} ${modelWithoutBrand}`.trim(), subtitle: '' };
  return {
    title: `${car.brand} ${tokens.slice(0, 2).join(' ')}`.trim(),
    subtitle: tokens.slice(2).join(' ')
  };
}

const officialModelImages = {
  'audi|a6 e tron': 'https://emea-dam.audi.com/adobe/assets/urn%3Aaaid%3Aaem%3Ae612f1f3-4da1-4dfe-8a79-98263358da52/as/A6e_2023_6005_2-L-1new.png?width=900',
  'audi|q4 e tron': 'https://emea-dam.audi.com/adobe/assets/urn%3Aaaid%3Aaem%3A721970fe-5699-42d3-935f-ed2d1e23b967/as/Q4e_2026_8393-L.jpg?width=900',
  'audi|q6 e tron': 'https://emea-dam.audi.com/adobe/assets/urn%3Aaaid%3Aaem%3A68a393f0-d411-4ed0-8311-3d267ee6f56e/as/Q6_2023_5202-cast_2-L.jpg?width=900',
  'bmw|i4': 'https://www.bmw.se/sv/alla-modeller/i-series/i4/bmw-i4-gran-coupe/_jcr_content/root/maincontent/container/container_copy_copy_/image_copy_copy.coreimg.jpeg/1734511026809/g26-bev-mp-bmw-m-edrive-3to2-4.jpeg',
  'bmw|i5': 'https://bmw.scene7.com/is/image/BMW/g60-bev-tech-data-stage-ext-3-4-front%3A2to1?fit=constrain%2C1&fmt=webp&wid=1600',
  'bmw|ix1': 'https://bmw.scene7.com/is/image/BMW/iX1_2024_000216341_3000x2000%3A3to2?fit=constrain%2C1&fmt=webp&wid=1493',
  'bmw|ix3': 'https://bmw.scene7.com/is/image/BMW/na5_teaser_electric-cars%3A3to2?fit=constrain%2C1&fmt=webp&wid=1600',
  'cupra|born': 'https://www.cupraofficial.se/content/dam/public/cupra-website/cars/born-2026/cc-lite/mobile/N7N7_CB2.png',
  'ford|explorer': 'https://ford.se/rails/active_storage/blobs/redirect/eyJfcmFpbHMiOnsibWVzc2FnZSI6IkJBaHBBdXhnIiwiZXhwIjpudWxsLCJwdXIiOiJibG9iX2lkIn19--e43626d34439433cba020b9b9079ed1302a3d835/electric_explorer_1.jpg',
  'kia|ev3': 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/new-car/ev3/ev3-lansering-1920x1437.jpg',
  'kia|ev4': 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/new-car/ev4/ev4-design-2-1920x1080px.jpg',
  'kia|ev5': 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/new-car/ev5/kia-ev5-kampanj-2-1920x1437px.jpg',
  'kia|ev6': 'https://www.kia.com/content/dam/kwcms/kme/global/en/assets/360vr/ev6/my25/cv-pe-gtl-my25/WAF_wolf_gray_0000.jpg',
  'kia|ev9': 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/new-car/ev9/kia-ev9-asllani-1920x1437.jpg',
  'mazda|6e': 'https://mnd-assets.mynewsdesk.com/image/upload/c_fill%2Cdpr_auto%2Cf_auto%2Cg_auto%2Cq_auto%3Agood%2Cw_1200/nrci1rerwiprt5p9ogxc80',
  'mercedes benz|cla': 'https://media.oneweb.mercedes-benz.com/images/dynamic/europe/SE/174311/807/iris.png?BKGND=9&IMGT=P27&POV=BE040%2CPZM&cp=U7lLKRUtPa6KAFr8s_ubHw&q=COSY-EU-100-1713d0VXq5WFng9jfZobxEnlqHI5QqqrQCPPnU2Geplxm7skt0uBMlHB2rTNrApncZO5uoXPaC3MJyIzNTORX7j6bAbKVSI54vqt3sQLRcNR1axXjTQH1JV8Y8wOdpXiZbfjT4FIEgYg9QlPgPDk2EbeWmg7QsdhP1gUf%25ew6GEysuG0lYRatB2rxwcApn1aG5uodikC3Mf9OzNTE0z7j6lBIKVS2vsvqtpLkLRcuZPaxX3FwH1JN9o8wOjGXiZbWzG4FId74g9Qfz7Psg8oTnnBKVS1sUvaKkMRLHvvdLaxXEuaH1Jl3J8wO2C%25iZbpzi4FIucHg9Q3XzPDkVoiZC7%25M4F8SFTg9itk6PD4%25mSeWgB3tsdRHTcUfGUNXGE0GSJ0lBHVOB2A8cbAp5dRI5gZ8lXhRjwQZgVBUnRuoQ3pE7EJxJeRB5PVsRiD4Nhc8An&uni=m',
  'mercedes benz|eqa': 'https://upload.wikimedia.org/wikipedia/commons/9/97/Mercedes-Benz_EQA_250_%28H243%29_front.jpg',
  'polestar|2': 'https://www.polestar.com/dato-assets/94392/1736775615-og-polestar-2-26-overview-seo.png',
  'polestar|4': 'https://www.polestar.com/dato-assets/94392/1744019757-00-polestar-4-26-overview-seo.png',
  'renault|5': 'https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/hedin/distribution-cars/renaultsesite/startpage/boka-din-r5/stage-row-techno-dsk.jpg?h=720&iar=0&w=960',
  'skoda|elroq': 'https://cdn.skoda-auto.com/images/sites/svse-v2/b15b77bc-352f-4210-82b2-7a8068dc10f7/6475133cd3a262bb0fdf23ad583f473f',
  'skoda|enyaq': 'https://cdn.skoda-auto.com/images/sites/svse-v2/dfcf2d21-dd61-475c-a2ff-91789e8877de/7be1ae172e870d406e324859c872c27d',
  'tesla|model 3': 'https://digitalassets.tesla.com/tesla-contents/image/upload/f_auto,q_auto/Model-3-Main-Hero-Desktop-LHD.png',
  'tesla|model y': 'https://digitalassets.tesla.com/tesla-contents/image/upload/f_auto,q_auto/Model-Y-Main-Hero-Desktop-Global.png',
  'toyota|bz4x': 'https://scene7.toyota.eu/is/image/toyotaeurope/BZ0005a_25?fit=constrain&qlt=80&resMode=sharp2&wid=1600',
  'volkswagen|id 3': 'https://assets.volkswagen.com/is/image/volkswagenag/IN0459_id3_neo_standing_in_front_of_mountain_panorama_stage?Zml0PWNyb3AlMkMxJndpZD0xMjgwJmhlaT03MjAmZm10PWpwZWcmcWx0PTc5JmJmYz1vZmYmMmI5ZQ==',
  'volkswagen|id 4': 'https://assets.volkswagen.com/is/image/volkswagenag/ID4_16x9?Zml0PWNyb3AlMkMxJndpZD0xMjgwJmhlaT03MjAmZm10PWpwZWcmcWx0PTc5JmJmYz1vZmYmMmI5ZQ==',
  'volvo|es90': 'https://www.volvocars.com/images/cs/v3/assets/blt0feaa88e629251fc/blte1768aaa9c09e2f9/69205cf7e85a38500b82b83c/_0005_vin0020_34Front_745_ES90.jpg?branch=prod_alias&format=auto&iar=0&quality=85&w=1600',
  'volvo|ex30': 'https://www.volvocars.com/images/cs/v3/assets/blt0feaa88e629251fc/blt7b90b87d12b6a249/694150ece819e5e0f5b9ff71/my27ex30-hero-4-5.jpg?branch=prod_alias&format=auto&iar=0&quality=85&w=1600',
  'zeekr|7x': 'https://www.datocms-assets.com/128969/1758024550-2025_08_zeekr7x_7623_v001_fa_srgb.jpg?auto=format%2Ccompress%2Cenhance&fit=crop&q=65&w=1400'
};

function normalizeImageKey(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function officialImageFor(brand, model) {
  const key = `${normalizeImageKey(brand)}|${normalizeImageKey(model)}`;
  return officialModelImages[key] || null;
}

function normalizeNameToken(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
}

function normalizeVehicleNameKey(value, brand = '') {
  const brandKey = normalizeNameToken(brand);
  return String(value || '')
    .toLowerCase()
    .replace(/\b(suv|sportback|edition|advanced|business)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .split(' ')
    .filter((part) => part && normalizeNameToken(part) !== brandKey)
    .join('');
}

function stripLeadingBrand(brand, value) {
  const brandText = String(brand || '').trim();
  const text = String(value || '').trim();
  if (!brandText) return text;
  const pattern = new RegExp(`^${brandText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s+`, 'i');
  return text.replace(pattern, '').trim();
}

function displayModelName(brand, model, variantName) {
  const modelText = String(model || '').trim();
  const variantText = stripLeadingBrand(brand, variantName);
  if (!variantText) return modelText;

  const normalizedModel = normalizeNameToken(modelText);
  const normalizedVariant = normalizeNameToken(variantText);
  const vehicleModel = normalizeVehicleNameKey(modelText, brand);
  const vehicleVariant = normalizeVehicleNameKey(variantText, brand);
  if (
    !normalizedModel ||
    normalizedVariant === normalizedModel ||
    normalizedVariant.startsWith(normalizedModel) ||
    (vehicleModel && (vehicleVariant === vehicleModel || vehicleVariant.startsWith(vehicleModel)))
  ) {
    return variantText;
  }
  return `${modelText} ${variantText}`.trim();
}

function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

function verifiedNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  if (number === 0) return null;
  return Number.isFinite(number) ? number : null;
}

function transformPublicVariant(row) {
  const brand = row.brand;
  const variantName = row.variant_name || '';
  const model = displayModelName(brand, row.model, variantName);
  const rangeVerified = verifiedNumber(row.wltp_range_km);
  const price = Number(row.price_sek) || null;
  const dcVerified = verifiedNumber(row.dc_charge_kw);
  const cargoVerified = verifiedNumber(row.boot_liters);
  const towingVerified = verifiedNumber(row.tow_kg);
  const seats = Number(row.seats) || 5;
  const sourceQuote = row.source_quote || '';
  return {
    id: `${slug(brand)}-${slug(model)}`,
    canonicalKey: `${row.brand}|${row.model}|${row.variant_name}`,
    brand,
    model,
    body: row.body_type || 'Elbil',
    seats,
    price,
    range: rangeVerified || 0,
    rangeVerified,
    consumption: 16,
    dc: dcVerified || 0,
    dcVerified,
    cargo: cargoVerified || 0,
    cargoVerified,
    towing: towingVerified || 0,
    towingVerified,
    drivetrain: row.drivetrain || 'Ej verifierad',
    familyScore: cargoVerified ? Math.min(98, 55 + cargoVerified / 12) : 68,
    winterScore: row.drivetrain?.toLowerCase().includes('fyr') ? 92 : 76,
    commuteScore: rangeVerified ? Math.min(98, 55 + rangeVerified / 12) : 70,
    source: row.source_url || '#quality',
    sourceHash: row.source_hash,
    validationStatus: row.validation_status,
    verifiedAt: row.verified_at?.slice(0, 10) || 'Verifierad',
    image: officialImageFor(row.brand, row.model),
    marketSeen: row.market_seen,
    availableConfirmed: row.available_confirmed,
    discontinuedCandidate: row.discontinued_candidate,
    comingOrLowVolume: row.coming_or_low_volume,
    summary:
      sourceQuote
        ? `${sourceQuote.slice(0, 170)}${sourceQuote.length > 170 ? '...' : ''}`
        : 'Publicerad från canonical EV-databasen med Mobility Sweden som marknadsindex och officiell källa för specifikationer.'
  };
}

async function loadSupabaseCars() {
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

async function loadLocalPublicCars() {
  const response = await fetch(appPath('/data/public_ev_variants.json'), { cache: 'no-store' });
  if (!response.ok) return null;
  const payload = await response.json();
  const rows = Array.isArray(payload) ? payload : payload.records;
  if (!rows?.length) return null;
  return rows.map(transformPublicVariant);
}

async function loadPublicCars() {
  try {
    const supabaseCars = await loadSupabaseCars();
    if (supabaseCars?.length) return { cars: supabaseCars, source: 'supabase' };
  } catch (error) {
    console.warn('Supabase public data unavailable, falling back to static public export.', error);
  }
  const localCars = await loadLocalPublicCars();
  if (localCars?.length) return { cars: localCars, source: 'local' };
  return null;
}

async function loadPipelineStatus() {
  const response = await fetch(appPath('/data/pipeline_status.json'), { cache: 'no-store' });
  if (!response.ok) return null;
  return response.json();
}

async function requestAdvisor(advisor) {
  const payload = {
    prompt: advisor.prompt,
    budget: advisor.budget,
    range: advisor.range,
    need: advisor.need
  };
  const endpoints = [appPath('/api/advisor'), 'http://127.0.0.1:8787/api/advisor'];
  let lastError;
  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(`AI-rådgivaren svarade ${response.status}`);
      return response.json();
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

async function requestCompareReport(cars) {
  const payload = {
    variant_keys: cars.map((car) => car.canonicalKey).filter(Boolean)
  };
  const endpoints = [appPath('/api/compare'), 'http://127.0.0.1:8787/api/compare'];
  let lastError;
  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(`Jämförelserapporten svarade ${response.status}`);
      return response.json();
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

function localAdvisorResult(advisor, cars) {
  const prompt = advisor.prompt.toLowerCase();
  const shortlist = cars.slice(0, 3).map((car) => ({
    ...car,
    match_score: scoreCar(car, advisor),
    reasons: reasonsFor(car, advisor),
    tradeoffs: [
      car.price ? null : 'Officiellt svenskt pris saknas i databasen.',
      car.dcVerified === null ? 'DC-laddning saknar verifierat värde.' : null,
      prompt.includes('drag') && car.towingVerified === null ? 'Dragvikt saknar verifierat värde.' : null,
    ].filter(Boolean),
  }));
  return {
    mode: 'local',
    summary: 'Lokal AI-fallback: shortlist baserad på publicerade, validerade poster.',
    interpreted_requirements: {
      budget_sek: advisor.budget,
      min_range_km: advisor.range,
      use_case: advisor.need,
      notes: 'Om ett krav saknar verifierad data markeras det öppet i korten.',
    },
    shortlist,
  };
}

function buildLocalCompareReport(cars) {
  const compared = cars.map((car) => {
    const priceScore = car.price ? Math.max(0, 35 - (car.price / 1200000) * 20) : 10;
    const rangeScore = Math.min(30, ((car.rangeVerified || 0) / 700) * 30);
    const practicalScore = Math.min(25, ((car.cargoVerified || 0) / 700) * 12 + ((car.towingVerified || 0) / 2500) * 13);
    return {
      variant_key: car.canonicalKey,
      name: `${car.brand} ${car.model}`,
      price_sek: car.price,
      wltp_range_km: car.rangeVerified,
      source_url: car.source,
      decision_score: Math.round(priceScore + rangeScore + practicalScore),
    };
  }).sort((a, b) => b.decision_score - a.decision_score);
  const winner = compared[0];
  return {
    mode: 'local',
    summary: winner ? `${winner.name} får högst lokal beslutsmatchning baserat på verifierade pris-, räckvidds- och praktikalitetsfält.` : 'Välj bilar för rapport.',
    winner,
    compared,
    reasons: ['Markerar starkast kombination av pris, räckvidd och praktisk användning i den valda jämförelsen.'],
    tradeoffs: ['Saknade fält räknas försiktigt och visas som uppgift saknas, inte som noll.'],
  };
}

function csvCell(value) {
  const text = value === null || value === undefined || value === '' ? 'Uppgift saknas' : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function exportCompareCsv(cars) {
  const headers = ['Bil', 'Pris från', 'WLTP km', 'DC kW', 'Dragvikt kg', 'Bagage liter', 'Källa'];
  const rows = cars.map((car) => [
    `${car.brand} ${car.model}`,
    car.price,
    car.rangeVerified,
    car.dcVerified,
    car.towingVerified,
    car.cargoVerified,
    car.source,
  ]);
  const csv = [headers, ...rows].map((row) => row.map(csvCell).join(',')).join('\n');
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `elbilsguiden-jamforelse-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function decisionMetricsFor(car, cars = []) {
  const comparable = cars.filter((item) => item.rangeVerified);
  const averageRange = comparable.length
    ? Math.round(comparable.reduce((sum, item) => sum + item.rangeVerified, 0) / comparable.length)
    : null;
  const rangePer100k = car.price && car.rangeVerified ? (car.rangeVerified / (car.price / 100000)).toFixed(1) : null;
  const pricePerKm = car.price && car.rangeVerified ? Math.round(car.price / car.rangeVerified) : null;
  const verifiedFields = [
    car.price,
    car.rangeVerified,
    car.dcVerified,
    car.towingVerified,
    car.cargoVerified,
    car.sourceHash,
  ].filter((value) => value !== null && value !== undefined && value !== '').length;
  return [
    {
      label: 'Räckvidd per 100 000 kr',
      value: rangePer100k ? `${rangePer100k} km` : 'Uppgift saknas',
      note: 'Högre är bättre. Bygger på listpris och WLTP.',
    },
    {
      label: 'Pris per WLTP-km',
      value: pricePerKm ? `${pricePerKm.toLocaleString('sv-SE')} kr/km` : 'Uppgift saknas',
      note: 'Lägre är bättre. Kampanjer och leasing ingår inte.',
    },
    {
      label: 'Mot MVP-snitt',
      value: averageRange && car.rangeVerified ? `${car.rangeVerified - averageRange >= 0 ? '+' : ''}${car.rangeVerified - averageRange} km` : 'Uppgift saknas',
      note: averageRange ? `Snittet bland publicerade varianter är ${averageRange} km WLTP.` : 'Snitt saknas.',
    },
    {
      label: 'Datatäckning',
      value: `${verifiedFields}/6 fält`,
      note: 'Pris, räckvidd, laddning, dragvikt, bagage och källa.',
    },
  ];
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

const defaultFilters = { body: 'Alla', maxPrice: 750000, minRange: 0, towRequired: false, priceKnown: false, sort: 'match' };
const MAX_COMPARE = 3;
const BASE_URL = (import.meta.env.VITE_SITE_URL || 'https://swedish-ev-advisor.se').replace(/\/$/, '');
const APP_BASE_PATH = (import.meta.env.VITE_APP_BASE_PATH || '').replace(/\/$/, '');

function appPath(path) {
  if (!APP_BASE_PATH) return path;
  return `${APP_BASE_PATH}${path.startsWith('/') ? path : `/${path}`}`;
}

const segments = [
  {
    slug: 'familj',
    title: 'Bästa elbilarna för familj',
    description: 'Elbilar med bra lastutrymme, räckvidd och vardagsekonomi för svenska familjer.',
    predicate: (car) => car.familyScore >= 78 || car.cargo >= 450,
    advisorPatch: { need: 'familj', prompt: 'Vi söker en elbil för familj, barnstolar, packning och längre resor.' }
  },
  {
    slug: 'vinter',
    title: 'Elbilar för vinter och längre resor',
    description: 'Elbilar som passar nordiskt väder, hög räckvidd och trygg vinterkörning.',
    predicate: (car) => car.winterScore >= 84 || car.drivetrain === 'Fyrhjulsdrift',
    advisorPatch: { need: 'vinter', prompt: 'Jag vill ha en elbil för vintervägar, fjällresor och bra räckvidd.' }
  },
  {
    slug: 'dragkrok',
    title: 'Elbilar med dragkrok',
    description: 'Jämför elbilar med dragvikt för släp, cykelhållare och fritidsbehov.',
    predicate: (car) => car.towing >= 1000,
    advisorPatch: { prompt: 'Jag behöver en elbil med dragkrok och tydlig dragvikt.' }
  },
  {
    slug: 'under-500000',
    title: 'Elbilar under 500 000 kr',
    description: 'Verifierade elbilar i Sverige med prisnivå under 500 000 kr.',
    predicate: (car) => car.price && car.price <= 500000,
    advisorPatch: { budget: 500000, prompt: 'Jag vill hitta en prisvärd elbil under 500 000 kr.' }
  },
  {
    slug: 'lang-rackvidd',
    title: 'Elbilar med lång räckvidd',
    description: 'Elbilar med hög WLTP-räckvidd för pendling och långresor.',
    predicate: (car) => car.range >= 580,
    advisorPatch: { range: 580, prompt: 'Jag prioriterar lång räckvidd och smidig laddning på långresa.' }
  }
];

function getRoute() {
  let path = window.location.pathname.replace(/\/$/, '') || '/';
  if (APP_BASE_PATH && path.startsWith(APP_BASE_PATH)) {
    path = path.slice(APP_BASE_PATH.length).replace(/\/$/, '') || '/';
  }
  if (path.startsWith('/bilar/')) return { type: 'car', slug: path.split('/').pop() };
  if (path === '/bilar') return { type: 'cars' };
  if (path === '/jamfor') return { type: 'compare' };
  if (path === '/verifiering') return { type: 'verification' };
  const segment = segments.find((item) => `/${item.slug}` === path);
  if (segment) return { type: 'segment', segment };
  return { type: 'home' };
}

function navigate(path) {
  const nextPath = APP_BASE_PATH ? `${APP_BASE_PATH}${path === '/' ? '' : path}` : path;
  window.history.pushState({}, '', nextPath || '/');
  window.dispatchEvent(new PopStateEvent('popstate'));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function findCarBySlug(cars, routeSlug) {
  return cars.find((car) => {
    const fullSlug = slug(`${car.brand} ${car.model}`);
    return car.id === routeSlug || fullSlug === routeSlug || fullSlug.startsWith(`${routeSlug}-`);
  });
}

function setSeo({ title, description, jsonLd }) {
  document.title = title;
  const canonicalUrl = jsonLd?.url || (Array.isArray(jsonLd) ? jsonLd.find((item) => item?.url)?.url : null) || `${BASE_URL}${window.location.pathname}`;
  let descriptionTag = document.querySelector('meta[name="description"]');
  if (!descriptionTag) {
    descriptionTag = document.createElement('meta');
    descriptionTag.setAttribute('name', 'description');
    document.head.appendChild(descriptionTag);
  }
  descriptionTag.setAttribute('content', description);

  let canonicalTag = document.querySelector('link[rel="canonical"]');
  if (!canonicalTag) {
    canonicalTag = document.createElement('link');
    canonicalTag.setAttribute('rel', 'canonical');
    document.head.appendChild(canonicalTag);
  }
  canonicalTag.setAttribute('href', canonicalUrl);

  const upsertMeta = (selector, attrs) => {
    let node = document.querySelector(selector);
    if (!node) {
      node = document.createElement('meta');
      Object.entries(attrs.identity).forEach(([key, value]) => node.setAttribute(key, value));
      document.head.appendChild(node);
    }
    node.setAttribute('content', attrs.content);
  };
  upsertMeta('meta[property="og:title"]', { identity: { property: 'og:title' }, content: title });
  upsertMeta('meta[property="og:description"]', { identity: { property: 'og:description' }, content: description });
  upsertMeta('meta[property="og:url"]', { identity: { property: 'og:url' }, content: canonicalUrl });
  upsertMeta('meta[name="twitter:title"]', { identity: { name: 'twitter:title' }, content: title });
  upsertMeta('meta[name="twitter:description"]', { identity: { name: 'twitter:description' }, content: description });

  document.querySelectorAll('script[data-jsonld="page"]').forEach((node) => node.remove());
  if (jsonLd) {
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.dataset.jsonld = 'page';
    script.textContent = JSON.stringify(jsonLd);
    document.head.appendChild(script);
  }
}

function carJsonLd(car) {
  const properties = [
    car.rangeVerified ? { '@type': 'PropertyValue', name: 'WLTP-räckvidd', value: `${car.rangeVerified} km` } : null,
    car.dcVerified ? { '@type': 'PropertyValue', name: 'DC-laddning', value: `${car.dcVerified} kW` } : null,
    car.towingVerified ? { '@type': 'PropertyValue', name: 'Dragvikt', value: `${car.towingVerified} kg` } : null,
    car.cargoVerified ? { '@type': 'PropertyValue', name: 'Bagage', value: `${car.cargoVerified} liter` } : null
  ].filter(Boolean);
  return {
    '@context': 'https://schema.org',
    '@type': 'Vehicle',
    name: `${car.brand} ${car.model}`,
    brand: { '@type': 'Brand', name: car.brand },
    model: car.model,
    image: car.image || undefined,
    url: `${BASE_URL}/bilar/${car.id}`,
    vehicleSeatingCapacity: car.seats,
    offers: car.price
      ? {
          '@type': 'Offer',
          price: car.price,
          priceCurrency: 'SEK',
          availability: 'https://schema.org/InStock',
          url: `${BASE_URL}/bilar/${car.id}`
        }
      : undefined,
    additionalProperty: properties
  };
}

function App() {
  const [cars, setCars] = useState(fallbackCars);
  const [route, setRoute] = useState(getRoute);
  const [dataNotice, setDataNotice] = useState('Visar lokal fallbackdata tills Supabase public views är konfigurerade.');
  const [advisor, setAdvisor] = useState({
    prompt: 'Vi är en familj i Stockholm med två barn, kör till fjällen ibland och vill ha dragkrok.',
    budget: 620000,
    range: 520,
    need: 'familj'
  });
  const [advisorResult, setAdvisorResult] = useState(null);
  const [advisorStatus, setAdvisorStatus] = useState({ state: 'idle', message: '' });
  const [compareReport, setCompareReport] = useState(null);
  const [compareReportStatus, setCompareReportStatus] = useState({ state: 'idle', message: '' });
  const [pipelineStatus, setPipelineStatus] = useState(null);
  const [filters, setFilters] = useState(defaultFilters);
  const [compare, setCompare] = useState(['tesla-model-y-lr-rwd', 'kia-ev3-long-range', 'polestar-2-lr-sm']);
  const resetFilters = () => setFilters(defaultFilters);

  useEffect(() => {
    const onPopState = () => setRoute(getRoute());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    loadPublicCars()
      .then((result) => {
        if (!result?.cars?.length) return;
        setCars(result.cars);
        setCompare(result.cars.slice(0, 3).map((car) => car.id));
        setDataNotice(
          result.source === 'supabase'
            ? 'Visar publicerade elbilar från Supabase public views.'
            : `Visar ${result.cars.length} publicerade varianter från lokal canonical-export.`
        );
      })
      .catch((error) => {
        setDataNotice(`Visar lokal fallbackdata. ${error.message}`);
      });
  }, []);

  useEffect(() => {
    loadPipelineStatus()
      .then((status) => {
        if (status) setPipelineStatus(status);
      })
      .catch(() => {
        setPipelineStatus(null);
      });
  }, []);

  const effectiveAdvisor = useMemo(() => {
    if (route.type !== 'segment') return advisor;
    return { ...advisor, ...route.segment.advisorPatch };
  }, [advisor, route]);

  const ranked = useMemo(() => {
    return cars
      .filter((car) => route.type !== 'segment' || route.segment.predicate(car))
      .map((car) => ({ ...car, score: scoreCar(car, effectiveAdvisor), reasons: reasonsFor(car, effectiveAdvisor) }))
      .filter((car) => filters.body === 'Alla' || car.body === filters.body)
      .filter((car) => !car.price || car.price <= filters.maxPrice)
      .filter((car) => car.range >= filters.minRange)
      .filter((car) => !filters.towRequired || car.towing > 0)
      .filter((car) => !filters.priceKnown || !!car.price)
      .sort((a, b) => {
        if (filters.sort === 'price') return (a.price || 9999999) - (b.price || 9999999);
        if (filters.sort === 'range') return b.range - a.range;
        if (filters.sort === 'efficiency') return a.consumption - b.consumption;
        return b.score - a.score;
      });
  }, [cars, effectiveAdvisor, filters, route]);

  const compareCars = compare.map((id) => cars.find((car) => car.id === id)).filter(Boolean);
  const topCar = ranked[0] ?? cars[0];
  const routeCar = route.type === 'car' ? findCarBySlug(cars, route.slug) : null;

  async function runAdvisor() {
    setAdvisorStatus({ state: 'loading', message: 'AI-rådgivaren analyserar publicerade, verifierade bilar...' });
    try {
      const result = await requestAdvisor(effectiveAdvisor);
      setAdvisorResult(result);
      setAdvisorStatus({
        state: 'ready',
        message: result.mode === 'openai' ? 'AI-råd skapat från validerad canonical-data.' : 'Lokal fallback skapad från validerad canonical-data.'
      });
    } catch (error) {
      setAdvisorResult(localAdvisorResult(effectiveAdvisor, ranked));
      setAdvisorStatus({
        state: 'ready',
        message: 'AI-API:t kunde inte nås, så en lokal shortlist visas från validerad canonical-data.'
      });
    }
  }

  async function runCompareReport() {
    if (!compareCars.length) {
      setCompareReport(buildLocalCompareReport(compareCars));
      setCompareReportStatus({ state: 'error', message: 'Välj minst en bil för att skapa en rapport.' });
      return;
    }
    setCompareReportStatus({ state: 'loading', message: 'Skapar beslutsrapport från publicerad canonical-data...' });
    try {
      const result = await requestCompareReport(compareCars);
      setCompareReport(result);
      setCompareReportStatus({
        state: 'ready',
        message: result.mode === 'openai' ? 'AI-rapport skapad från validerad canonical-data.' : 'Rapport skapad från validerad canonical-data.'
      });
    } catch (error) {
      setCompareReport(null);
      setCompareReportStatus({
        state: 'ready',
        message: 'AI-API:t kunde inte nås, så en lokal beslutsrapport visas från validerad canonical-data.'
      });
    }
  }

  useEffect(() => {
    if (route.type === 'car') {
      if (routeCar) {
        setSeo({
          title: `${routeCar.brand} ${routeCar.model} – pris, räckvidd och specs | Elbilsguiden`,
          description: `${routeCar.brand} ${routeCar.model}: jämför pris, WLTP-räckvidd, laddning, dragvikt och bagage med verifierade svenska källor.`,
          jsonLd: carJsonLd(routeCar)
        });
        return;
      }
    }
    if (route.type === 'segment') {
      setSeo({
        title: `${route.segment.title} | Elbilsguiden`,
        description: route.segment.description,
        jsonLd: {
          '@context': 'https://schema.org',
          '@type': 'CollectionPage',
          name: route.segment.title,
          description: route.segment.description,
          url: `${BASE_URL}/${route.segment.slug}`
        }
      });
      return;
    }
    setSeo({
      title: 'Elbilsguiden Sverige – hitta rätt elbil med AI',
      description: 'Beskriv budget, körning och behov och få en shortlist med verifierade elbilar, tydliga kompromisser och källor.',
      jsonLd: {
        '@context': 'https://schema.org',
        '@type': 'WebApplication',
        name: 'Elbilsguiden Sverige',
        applicationCategory: 'AutomotiveApplication',
        operatingSystem: 'Web'
      }
    });
  }, [route, routeCar]);

  function toggleCompare(id) {
    setCompare((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (current.length >= MAX_COMPARE) return [...current.slice(1), id];
      return [...current, id];
    });
  }
  const compareLimitReached = compare.length >= MAX_COMPARE;

  return (
    <main>
      <header className={`siteHeader ${route.type === 'car' ? 'siteHeaderCinematic' : ''}`}>
        <button className="brand brandButton" type="button" onClick={() => navigate('/')}>
          <span className="brandMark"><Zap size={18} /></span>
          <span>Elbilsguiden</span>
        </button>
        <nav>
          <button onClick={() => navigate('/bilar')}>Bilar</button>
          <button onClick={() => navigate('/jamfor')}>Jämför</button>
          <button onClick={() => navigate('/verifiering')}>Verifiering</button>
        </nav>
      </header>

      {route.type === 'car' ? (
        <CarDetailPage
          car={routeCar}
          cars={cars}
          onCompare={toggleCompare}
          selected={routeCar ? compare.includes(routeCar.id) : false}
        />
      ) : (
        <>

      {route.type === 'home' && (
        <HeroSearch
          advisor={effectiveAdvisor}
          setAdvisor={setAdvisor}
          shortlist={ranked.slice(0, 3)}
          advisorResult={advisorResult}
          advisorStatus={advisorStatus}
          onRunAdvisor={runAdvisor}
        />
      )}

      {route.type === 'segment' && <SegmentHeader segment={route.segment} count={ranked.length} />}
      {route.type === 'verification' && <VerificationPage status={pipelineStatus} />}

      {route.type === 'home' && <section className="needSection">
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
      </section>}

      {route.type === 'home' && <AiAdvisorPanel />}

      {route.type !== 'compare' && route.type !== 'verification' && <section className="carsSection" id="cars">
        <div className="sectionIntro wide">
          <span className="eyebrow">Elbilar</span>
          <h2>Utforska verifierade elbilar i Sverige.</h2>
          <p>Kort först, tabell sen. Filtrera på det som faktiskt påverkar vardagen.</p>
          <p className="dataNotice" aria-live="polite">{dataNotice}</p>
          <details className="scoreInfo">
            <summary>Hur räknas matchningspoängen?</summary>
            <p>
              Poängen viktar fyra delar mot varandra: budget (max 30 p), räckvidd (max 22 p),
              valt behov — familj, pendling eller vinter (max 25 p) och nyckelord i din
              behovsbeskrivning som "drag", "barn", "billig" eller "vinter" (max 23 p).
              Maxpoäng är 100.
            </p>
          </details>
        </div>
        <div className="carsLayout">
          <FilterSidebar
            filters={filters}
            setFilters={setFilters}
            resultCount={ranked.length}
            totalCount={cars.length}
            onReset={resetFilters}
          />
          <div className="carsResults">
            <div className="carsToolbar">
              <strong>{ranked.length} verifierade matchningar</strong>
              <span>
                {filters.minRange ? `Minst ${filters.minRange} km · ` : ''}
                {filters.towRequired ? 'Dragvikt krävs · ' : ''}
                {filters.priceKnown ? 'Endast med pris · ' : ''}
                Sorterat efter {filters.sort === 'match' ? 'smart matchning' : filters.sort === 'price' ? 'lägst pris' : filters.sort === 'range' ? 'längst räckvidd' : 'lägst förbrukning'}
              </span>
            </div>
            <div className="carGrid">
              {ranked.length === 0 ? (
                <div className="emptyState">
                  <p>Inga bilar matchar dina filter just nu.</p>
                  <button onClick={resetFilters}>Återställ filter</button>
                </div>
              ) : (
                ranked.map((car) => (
                <CarCard
                  key={car.id}
                  car={car}
                  advisor={effectiveAdvisor}
                  selected={compare.includes(car.id)}
                  onCompare={() => toggleCompare(car.id)}
                  compareLimitReached={!compare.includes(car.id) && compareLimitReached}
                  />
                ))
              )}
            </div>
          </div>
        </div>
      </section>
      }

      <CompareBar cars={compareCars} onRemove={toggleCompare} onClear={() => setCompare([])} />

      {(route.type === 'home' || route.type === 'compare') && <section className="compareSection" id="compare">
        <div className="decisionReport">
          <div>
            <span className="eyebrow">Beslutsrapport</span>
            <h2>Jämför sida vid sida</h2>
            <p>
              Sammanfattningen väger räckvidd, budget, laddning, lastutrymme och nordiska behov
              mot varandra innan tabellen visar detaljerna.
            </p>
          </div>
          <div className="reportCard">
            <Sparkles size={22} />
            <h3>Rekommendation</h3>
            <RecommendationText
              cars={compareCars}
              report={compareReport}
              status={compareReportStatus}
              onRunReport={runCompareReport}
              onExportCsv={() => exportCompareCsv(compareCars)}
            />
          </div>
        </div>
        <ComparisonTable cars={compareCars} />
      </section>}

{route.type === 'home' && <section className="qualitySection compactTrust" id="quality">
        <div>
          <span className="eyebrow">Tryggare val</span>
          <h2>Verifierade uppgifter, tydliga luckor.</h2>
          <p>
            Vi visar bara publicerade biluppgifter med källor. Saknas ett värde står det “Uppgift saknas”,
            inte missvisande nollor.
          </p>
        </div>
        <div className="trustPills" aria-label="Datakvalitet">
          <span><BadgeCheck size={16} /> Källor visas</span>
          <span><ShieldCheck size={16} /> Bara publicerad data</span>
          <button type="button" onClick={() => navigate('/verifiering')}>Så kontrolleras datan <ArrowRight size={16} /></button>
        </div>
      </section>}
      </>
      )}

      <footer>
        <span><ShieldCheck size={16} /> Oberoende beslutsstöd med verifierade källor.</span>
        <button type="button" onClick={() => navigate('/')}><Home size={16} /> Till toppen</button>
      </footer>
    </main>
  );
}

function HeroSearch({ advisor, setAdvisor, shortlist, advisorResult, advisorStatus, onRunAdvisor }) {
  const topCar = shortlist[0] ?? fallbackCars[0];
  const advisorShortlist = advisorResult?.shortlist ?? [];
  const heroShortlist = (advisorShortlist.length ? advisorShortlist : shortlist.length ? shortlist : [fallbackCars[0]]).slice(0, 2);
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
            placeholder="Beskriv dina behov, t.ex. “familjebil under 650 000 kr, minst 550 km räckvidd, dragkrok och bra vinteregenskaper”."
            rows="3"
          />
        </div>
        <p className="advisorHint">Beskriv dina behov – AI tolkar kraven, visar osäker data öppet och ger en källbunden shortlist.</p>
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
        <div className="advisorActions">
          <button className="primaryCta" type="button" onClick={onRunAdvisor} disabled={advisorStatus.state === 'loading'}>
            {advisorStatus.state === 'loading' ? 'Analyserar...' : 'Få AI-shortlist'} <Sparkles size={18} />
          </button>
          <a className="secondaryCta" href="#cars">
            Visa alla matchningar <ArrowRight size={18} />
          </a>
        </div>
        {advisorStatus.message && (
          <p className={`advisorStatus ${advisorStatus.state}`} aria-live="polite">{advisorStatus.message}</p>
        )}
        <div className="mockResponse">
          <div>
            <h3>Tolkade krav</h3>
            <div className="requirementChips">
              {requirementChips.map((chip) => <span key={chip}>{chip}</span>)}
            </div>
            {advisorResult?.interpreted_requirements?.notes && (
              <p className="advisorNote">{advisorResult.interpreted_requirements.notes}</p>
            )}
          </div>
          <div>
            <div className="shortlistHeader">
              <h3>{advisorShortlist.length ? 'AI-shortlist' : 'Preliminär shortlist'}</h3>
              {advisorResult?.mode && <span>{advisorResult.mode === 'openai' ? 'OpenAI' : 'Fallback'}</span>}
            </div>
            {advisorResult?.summary && <p className="advisorSummary">{advisorResult.summary}</p>}
            <div className="advisorResultGrid">
              {heroShortlist.map((car, index) => (
                <AdvisorResultCard key={car.id} car={car} rank={index + 1} />
              ))}
            </div>
          </div>
        </div>
      </div>
      <aside className="heroRecommendation">
        <span>Bästa match just nu</span>
        <CarImage car={topCar} />
        <h2>{topCar.brand} {topCar.model}</h2>
        <p>{topCar.summary}</p>
      </aside>
    </section>
  );
}

function AdvisorResultCard({ car, rank }) {
  const sourceUrl = car.source_url || car.source;
  const matchScore = Math.round(car.match_score ?? car.score ?? 0);
  const primaryReason = car.reasons?.[0] ?? 'Stark totalmatchning med verifierade uppgifter.';
  const tradeoff = car.tradeoffs?.[0] ?? 'Jämför detaljerna mot dina krav innan beslut.';

  return (
    <article className="advisorResultCard">
      <div className="advisorResultTop">
        <span className="rankPill">#{rank}</span>
        <strong>{car.brand} {car.model} {car.variant_name ?? ''}</strong>
        {!!matchScore && <span className="matchPill">{matchScore}%</span>}
      </div>
      <div className="advisorSignals">
        <div>
          <span>Matchar</span>
          <p>{primaryReason}</p>
        </div>
        <div>
          <span>Kompromiss</span>
          <p>{tradeoff}</p>
        </div>
      </div>
      <div className="advisorResultFooter">
        <span><BadgeCheck size={13} /> Canonical-data</span>
        {sourceUrl && (
          <a href={sourceUrl} target="_blank" rel="noreferrer">
            Källa <ExternalLink size={13} />
          </a>
        )}
      </div>
    </article>
  );
}

function AiAdvisorPanel() {
  return (
    <section className="advisorPanel">
      <ConsumerStep icon={Search} title="Beskriv dina behov" text="Skriv fritt om budget, familj, pendling, resor, dragkrok och laddning." />
      <ConsumerStep icon={Sparkles} title="Få en shortlist" text="Rådgivaren väljer ut 2–3 relevanta bilar och förklarar kompromisserna." />
      <ConsumerStep icon={BadgeCheck} title="Jämför med källor" text="Se pris, räckvidd, laddning, bagage och verifieringsdatum innan du går vidare." />
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

function FilterSidebar({ filters, setFilters, resultCount, totalCount, onReset }) {
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
        Minsta räckvidd
        <input
          type="range"
          min="0"
          max="1000"
          step="20"
          value={filters.minRange}
          onChange={(event) => setFilters({ ...filters, minRange: Number(event.target.value) })}
        />
        <strong>{filters.minRange ? `${filters.minRange} km` : 'Alla'}</strong>
      </label>
      <div className="filterToggles">
        <label>
          <input
            type="checkbox"
            checked={filters.towRequired}
            onChange={(event) => setFilters({ ...filters, towRequired: event.target.checked })}
          />
          Dragvikt angiven
        </label>
        <label>
          <input
            type="checkbox"
            checked={filters.priceKnown}
            onChange={(event) => setFilters({ ...filters, priceKnown: event.target.checked })}
          />
          Pris angivet
        </label>
      </div>
      <label>
        Sortera
        <select value={filters.sort} onChange={(event) => setFilters({ ...filters, sort: event.target.value })}>
          <option value="match">Smart matchning</option>
          <option value="price">Lägst pris</option>
          <option value="range">Längst räckvidd</option>
          <option value="efficiency">Lägst förbrukning</option>
        </select>
      </label>
      <div className="filterFooter">
        <span>{resultCount} av {totalCount} {resultCount === 1 ? 'bil' : 'bilar'}</span>
        <button type="button" onClick={onReset}>Återställ</button>
      </div>
    </aside>
  );
}

function decisionSignalsFor(car, advisor = {}) {
  const budget = advisor.budget ?? 0;
  const minRange = advisor.range ?? 0;
  const wantsTow = String(advisor.prompt || '').toLowerCase().includes('drag');
  const signals = [];

  if (car.price && budget && car.price <= budget) signals.push({ type: 'good', label: 'Inom budget' });
  if (car.price && budget && car.price > budget) signals.push({ type: 'watch', label: 'Över budget' });
  if (!car.price) signals.push({ type: 'warn', label: 'Pris saknas' });
  if (minRange && car.range >= minRange) signals.push({ type: 'good', label: 'Klarar räckvidd' });
  if (minRange && car.range < minRange) signals.push({ type: 'watch', label: 'Kortare räckvidd' });
  if (car.towing > 0) signals.push({ type: wantsTow ? 'good' : 'neutral', label: 'Dragvikt finns' });
  if (wantsTow && !car.towing) signals.push({ type: 'warn', label: 'Dragvikt saknas' });
  if (car.sourceHash || ['published', 'published_reviewed'].includes(car.validationStatus)) {
    signals.push({ type: 'verified', label: 'Källa verifierad' });
  }

  return signals.slice(0, 5);
}

function marketStatusFor(car) {
  const statuses = [];
  if (car.marketSeen) {
    statuses.push({ type: 'market', label: 'Registrerad i Sverige', title: 'Modellen finns i Mobility Swedens registreringsdata.' });
  }
  if (car.availableConfirmed) {
    statuses.push({ type: 'available', label: 'Tillgänglighet bekräftad', title: 'Tillverkare/importör bekräftar aktuell tillgänglighet.' });
  } else {
    statuses.push({ type: 'unconfirmed', label: 'Tillgänglighet ej bekräftad', title: 'Marknadsnärvaro finns, men aktuell tillgänglighet är inte separat bekräftad.' });
  }
  if (car.comingOrLowVolume) {
    statuses.push({ type: 'low', label: 'Kommande/låg volym', title: 'Modellen har låg registreringsvolym eller är på väg in.' });
  }
  if (car.discontinuedCandidate) {
    statuses.push({ type: 'watch', label: 'Möjlig utfasning', title: 'Registreringsmönster eller källstatus gör att modellen bör bevakas.' });
  }
  return statuses;
}

function MarketStatusBadges({ car, compact = false }) {
  return (
    <div className={`marketStatusBadges ${compact ? 'compact' : ''}`} aria-label="Marknads- och tillgänglighetsstatus">
      {marketStatusFor(car).map((status) => (
        <span key={status.label} className={`marketStatusBadge ${status.type}`} title={status.title}>
          {status.type === 'available' || status.type === 'market' ? <BadgeCheck size={12} /> : <ShieldCheck size={12} />}
          {status.label}
        </span>
      ))}
    </div>
  );
}

function CarCard({ car, advisor, selected, onCompare, compareLimitReached }) {
  const decisionSignals = decisionSignalsFor(car, advisor);
  const highlightBadges = [
    car.rangeVerified >= 650 ? 'Lång räckvidd' : null,
    car.towingVerified >= 2000 ? 'Stark dragvikt' : null,
    car.cargoVerified >= 650 ? 'Rymligt bagage' : null,
  ].filter(Boolean);

  return (
    <article className="carCard">
      <div className="carImageWrap">
        <CarImage car={car} />
        <div className="matchBadge" title="Viktning: budget 30 + räckvidd 22 + behov 25 + krav 23">
          {car.score}% match
        </div>
      </div>
      <div className="carContent">
        <div className="carTopline">
          <span>{car.body}</span>
          <VerificationBadge compact date={car.verifiedAt} />
        </div>
        <h3>{car.brand} {car.model}</h3>
        <MarketStatusBadges car={car} compact />
        <div className="decisionSignals" aria-label="Beslutssignaler">
          {decisionSignals.map((signal) => (
            <span key={signal.label} className={`decisionSignal ${signal.type}`}>
              {signal.type === 'good' || signal.type === 'verified' ? <Check size={12} /> : <ShieldCheck size={12} />}
              {signal.label}
            </span>
          ))}
        </div>
        {highlightBadges.length > 0 && (
          <div className="carHighlightBadges" aria-label="Styrkor">
            {highlightBadges.map((badge) => <span key={badge}>{badge}</span>)}
          </div>
        )}
        <p>{car.summary}</p>
        {!car.price && <p className="missingDataNote">Pris saknas: inget säkert officiellt svenskt pris är publicerat i databasen ännu.</p>}
        <div className="metricGrid">
          <Metric label="Pris från" value={car.price ? formatSEK(car.price) : 'Ej angivet'} />
          <Metric label="WLTP" value={detailValue(car.rangeVerified, 'km')} />
          <Metric label="DC" value={detailValue(car.dcVerified, 'kW')} />
          <Metric label="Dragvikt" value={detailValue(car.towingVerified, 'kg')} />
          <Metric label="Bagage" value={detailValue(car.cargoVerified, 'l')} />
          <Metric label="Verifierad" value={car.verifiedAt} />
        </div>
        <ul>
          {car.reasons.map((reason) => (
            <li key={reason}><Check size={15} /> {reason}</li>
          ))}
        </ul>
        <div className="cardActions">
          <a href={car.source} target="_blank" rel="noreferrer">
            Källa <ExternalLink size={15} />
          </a>
          <button onClick={() => navigate(`/bilar/${car.id}`)}>Bilsida <ChevronRight size={15} /></button>
          <button
            onClick={onCompare}
            aria-pressed={selected}
            title={compareLimitReached ? 'Ersätter äldsta valet i jämförelsen' : undefined}
          >
            {selected ? 'Vald' : compareLimitReached ? 'Byt in' : 'Jämför'} <ChevronRight size={15} />
          </button>
        </div>
      </div>
    </article>
  );
}

function SegmentHeader({ segment, count }) {
  return (
    <section className="segmentHeader">
      <span className="eyebrow">Guide</span>
      <h1>{segment.title}</h1>
      <p>{segment.description}</p>
      <strong>{count} verifierade bilar matchar segmentet.</strong>
    </section>
  );
}

function VerificationPage({ status }) {
  return (
    <section className="verificationPage">
      <div className="sectionIntro wide">
        <span className="eyebrow">Verifiering</span>
        <h1>Så säkras datan innan den visas publikt.</h1>
        <p>
          Elbilsguiden använder Mobility Sweden som svenskt marknadsindex och officiella svenska
          tillverkar- eller importörskällor för pris och specifikationer. AI får föreslå strukturerad
          extraktion, men osäkra eller ofullständiga värden stoppas i granskning.
        </p>
      </div>
      <PipelineStatusPanel status={status} />
      <div className="verificationGrid">
        <QualityStep icon={CarFront} title="1. Marknadsnärvaro" text="Mobility Sweden visar vilka modeller som faktiskt syns i svensk nyregistrering. Det används aldrig som källa för pris eller specifikationer." />
        <QualityStep icon={ShieldCheck} title="2. Officiella källor" text="Pris, WLTP, laddning, bagage och dragvikt hämtas från tillverkare/importör, prislistor, tekniska PDF:er eller modell-/konfiguratorsidor." />
        <QualityStep icon={Sparkles} title="3. AI-extraktion" text="AI strukturerar informationen i staging-tabeller med källa, citat, hash och confidence. Rå AI-output visas inte publikt." />
        <QualityStep icon={BadgeCheck} title="4. Validering" text="Hårda regler stoppar orimliga värden. Saknade fält visas som “Uppgift saknas” i stället för missvisande nollor." />
      </div>
      <article className="verificationNote">
        <h2>Prislogik</h2>
        <p>
          Ordinarie listpris och kampanjpris ska hållas isär. I MVP:n visas bara publicerade prisfält som
          klarar käll- och valideringskraven. Om pris saknas betyder det att inget säkert officiellt svenskt
          pris finns publicerat i den canonical-post som visas.
        </p>
      </article>
    </section>
  );
}

function CarDetailPage({ car, cars, onCompare, selected }) {
  if (!car) {
    return (
      <section className="notFoundPage">
        <span className="eyebrow">404</span>
        <h1>Bilen finns inte i databasen.</h1>
        <p>Gå tillbaka till katalogen och välj en verifierad modell.</p>
        <button onClick={() => navigate('/bilar')}>Visa alla bilar</button>
      </section>
    );
  }

  const similarCars = cars
    .filter((item) => item.id !== car.id && (item.body === car.body || Math.abs(item.price - car.price) < 120000))
    .slice(0, 3);

  return (
    <div className="carDetailPage cinematicDetailPage">
      <section className="carDetailHero" style={car.image ? { '--hero-image': `url(${car.image})` } : undefined}>
        <div>
          <VerificationBadge />
          <h1>{splitCarTitle(car).title}{splitCarTitle(car).subtitle && <> <span>{splitCarTitle(car).subtitle}</span></>}</h1>
          <p>{car.summary}</p>
          <MarketStatusBadges car={car} />
          <div className="detailActions">
            <button onClick={() => onCompare(car.id)}>{selected ? 'Ta bort från jämförelse' : 'Lägg till i jämförelse'}</button>
            <a href={car.source} target="_blank" rel="noreferrer">Öppna källa <ExternalLink size={16} /></a>
          </div>
        </div>
        <CarImage car={car} />
      </section>

      <section className="detailStats">
        <Metric icon={Tag} label="Pris från" value={car.price ? formatSEK(car.price) : 'Ej angivet'} />
        <Metric icon={Route} label="WLTP-räckvidd" value={detailValue(car.rangeVerified, 'km')} />
        <Metric icon={PlugZap} label="DC-laddning" value={detailValue(car.dcVerified, 'kW')} />
        <Metric icon={ShieldCheck} label="Dragvikt" value={detailValue(car.towingVerified, 'kg')} />
        <Metric icon={Package} label="Bagage" value={detailValue(car.cargoVerified, 'liter')} />
        <Metric icon={BadgeCheck} label="Verifierad" value={car.verifiedAt} />
      </section>

      <AiSummaryCard car={car} />
      <DecisionMetricsCard car={car} cars={cars} />

      <section className="detailNarrative">
        <div>
          <span className="eyebrow">Passar bäst för</span>
          <h2>Varför den här bilen kan vara relevant</h2>
          <ul>
            {reasonsFor(car, { budget: car.price || 1200000, range: Math.min(car.range, 580), need: 'familj', prompt: 'drag barn vinter' }).map((reason) => (
              <li key={reason}><Check size={16} /> {reason}</li>
            ))}
          </ul>
        </div>
        <div>
          <span className="eyebrow">Datakälla</span>
          <h2>Verifiering</h2>
          <p>
            Specifikationer och pris ska komma från officiell svensk tillverkar- eller importörskälla.
            Mobility Sweden används endast för marknadsnärvaro.
          </p>
        </div>
      </section>

      <section className="detailSectionGrid" aria-label="Detaljerade specifikationer">
        <DetailInfoCard
          eyebrow="Specifikationer"
          title="Nyckeltal"
          source={car.source}
          verifiedAt={car.verifiedAt}
          items={[
            ['Pris från', car.price ? formatSEK(car.price) : 'Ej angivet'],
            ['Säten', detailValue(car.seats)],
            ['Drivlina', car.drivetrain || 'Uppgift saknas'],
            ['Kaross', car.body || 'Uppgift saknas']
          ]}
        />
        <DetailInfoCard
          eyebrow="Räckvidd och laddning"
          title="Energi i vardagen"
          source={car.source}
          verifiedAt={car.verifiedAt}
          items={[
            ['WLTP-räckvidd', detailValue(car.rangeVerified, 'km')],
            ['DC-laddning', detailValue(car.dcVerified, 'kW')],
            ['AC-laddning', 'Uppgift saknas'],
            ['Förbrukning', car.consumption ? `${car.consumption} kWh/100 km` : 'Uppgift saknas']
          ]}
        />
        <DetailInfoCard
          eyebrow="Praktikalitet"
          title="Last och fritid"
          source={car.source}
          verifiedAt={car.verifiedAt}
          items={[
            ['Dragvikt', detailValue(car.towingVerified, 'kg')],
            ['Bagage', detailValue(car.cargoVerified, 'liter')],
            ['Familjepoäng', car.familyScore ? `${Math.round(car.familyScore)} / 100` : 'Uppgift saknas'],
            ['Vinterpoäng', car.winterScore ? `${Math.round(car.winterScore)} / 100` : 'Uppgift saknas']
          ]}
        />
        <SourceVerificationCard car={car} />
      </section>

      <section className="similarSection">
        <div className="sectionIntro wide">
          <span className="eyebrow">Liknande bilar</span>
          <h2>Jämför med närliggande alternativ.</h2>
        </div>
        <div className="carGrid">
          {similarCars.map((item) => (
            <CarCard
              key={item.id}
              car={{ ...item, score: scoreCar(item, { budget: car.price || 700000, range: car.range || 500, need: 'familj', prompt: '' }), reasons: reasonsFor(item, { budget: car.price || 700000, range: car.range || 500, need: 'familj', prompt: '' }) }}
              advisor={{ budget: car.price || 700000, range: car.range || 500, need: 'familj', prompt: '' }}
              selected={false}
              onCompare={() => onCompare(item.id)}
              compareLimitReached={false}
            />
          ))}
        </div>
      </section>
    </div>
  );
}

function AiSummaryCard({ car }) {
  const strengths = [
    car.rangeVerified ? `${car.rangeVerified} km WLTP enligt publicerad källa.` : null,
    car.towingVerified ? `Dragvikt upp till ${car.towingVerified} kg.` : null,
    car.cargoVerified ? `${car.cargoVerified} liter bagageutrymme.` : null,
    car.price ? `Pris från ${formatSEK(car.price)}.` : null
  ].filter(Boolean);
  const compromises = [
    !car.availableConfirmed ? 'Tillgänglighet är inte separat bekräftad i databasen.' : null,
    car.dcVerified === null ? 'DC-laddning saknas i databasen.' : null,
    car.towingVerified === null ? 'Dragvikt saknas i databasen.' : null
  ].filter(Boolean);
  return (
    <section className="aiSummaryCard">
      <div>
        <span className="eyebrow">AI-sammanfattning</span>
        <h2>Beslutsstöd för {car.brand} {car.model}</h2>
      </div>
      <div className="summaryColumns">
        <SummaryBlock title="Passar bäst för" items={reasonsFor(car, { budget: car.price || 1200000, range: Math.min(car.range || 580, 580), need: 'familj', prompt: 'drag barn vinter' })} />
        <SummaryBlock title="Viktiga styrkor" items={strengths.length ? strengths : ['Uppgift saknas i databasen.']} />
        <SummaryBlock title="Kompromisser" items={compromises.length ? compromises : ['Inga tydliga kompromisser i tillgänglig publicerad data.']} />
        <SummaryBlock title="Datavarningar" items={[car.sourceHash ? 'Källa och hash finns sparade.' : 'Uppgift saknas i databasen.']} />
      </div>
    </section>
  );
}

function DecisionMetricsCard({ car, cars }) {
  return (
    <section className="decisionMetricsCard">
      <div>
        <span className="eyebrow">Beslutsnyckeltal</span>
        <h2>Mer värde än bara specifikationer.</h2>
        <p>Nyckeltalen räknas bara på validerade publicerade fält och ska ses som stöd, inte som offert.</p>
      </div>
      <div className="decisionMetricGrid">
        {decisionMetricsFor(car, cars).map((metric) => (
          <article key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <p>{metric.note}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function SummaryBlock({ title, items }) {
  return (
    <div>
      <h3>{title}</h3>
      <ul>
        {items.map((item) => <li key={item}><Check size={15} /> {item}</li>)}
      </ul>
    </div>
  );
}

function DetailInfoCard({ eyebrow, title, items, source, verifiedAt }) {
  return (
    <article className="detailInfoCard">
      <span className="eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      <dl>
        {items.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {(source || verifiedAt) && (
        <p className="sectionSource">
          {verifiedAt ? `Senast verifierad ${verifiedAt}. ` : ''}
          {source && <a href={source} target="_blank" rel="noreferrer">Visa källa <ExternalLink size={13} /></a>}
        </p>
      )}
    </article>
  );
}

function SourceVerificationCard({ car }) {
  return (
    <article className="detailInfoCard sourceVerificationCard" id="quality">
      <span className="eyebrow">Källor och verifiering</span>
      <h2>Verifierad datakedja</h2>
      <p>Specifikationer och pris visas från publicerade canonical-poster. Mobility Sweden används bara för marknadsnärvaro, inte som specifikationskälla.</p>
      <a href={car.source} target="_blank" rel="noreferrer">Öppna officiell källa <ExternalLink size={16} /></a>
    </article>
  );
}

function CarImage({ car }) {
  if (car?.image) {
    return <img src={car.image} alt={`${car.brand} ${car.model}`} />;
  }
  return (
    <div className="missingCarImage" role="img" aria-label={`Verifierad bild saknas for ${car?.brand ?? ''} ${car?.model ?? ''}`.trim()}>
      <CarFront size={28} />
      <span>Bild saknas</span>
    </div>
  );
}

function Metric({ icon: Icon, label, value }) {
  const missing = value === 'Uppgift saknas' || value === 'Ej angivet';
  return (
    <div className={`metricItem ${missing ? 'isMissing' : ''}`} title={missing ? 'Tillverkaren/importören har inte ett verifierat publicerat värde i databasen.' : undefined}>
      {Icon && <Icon size={20} aria-hidden="true" />}
      <span>{label}</span>
      <strong>{value}</strong>
      {missing && <small>Ej verifierat</small>}
    </div>
  );
}

function CompareBar({ cars, onRemove, onClear }) {
  if (cars.length === 0) return null;
  return (
    <div className="compareBar">
      <span>{cars.length} av {MAX_COMPARE} valda</span>
      <div>
        {cars.map((car) => (
          <button key={car.id} type="button" onClick={() => onRemove(car.id)} title="Ta bort från jämförelsen">
            {car.brand} {car.model}
          </button>
        ))}
      </div>
      <button type="button" className="clearCompare" onClick={onClear}>Rensa</button>
      <button type="button" onClick={() => navigate('/jamfor')}>Öppna rapport <ArrowRight size={16} /></button>
    </div>
  );
}

function RecommendationText({ cars, report, status, onRunReport, onExportCsv }) {
  if (cars.length === 0) {
    return <p>Välj upp till tre bilar i listan ovan så sammanfattar vi kompromisserna här.</p>;
  }
  if (report?.winner) {
    const winner = report.winner;
    const compared = report.compared ?? [];
    const winnerCompared = compared.find((item) => item.variant_key === winner.variant_key);
    const alternative = compared.find((item) => item.variant_key !== winner.variant_key);
    const primaryReason = report.reasons?.[0] ?? 'Starkast helhetsbalans i jämförelsen.';
    const primaryTradeoff = report.tradeoffs?.[0] ?? 'Kontrollera detaljerna mot dina egna krav innan beslut.';

    return (
      <div className="reportBody">
        <div className="reportWinner">
          <span><Sparkles size={14} /> Bäst val</span>
          <strong>{winner.name}</strong>
          <p>{report.summary}</p>
          {winner.source_url && (
            <a href={winner.source_url} target="_blank" rel="noreferrer">
              Källa <ExternalLink size={13} />
            </a>
          )}
        </div>
        <div className="reportInsightGrid">
          <ReportInsightCard title="Varför" text={primaryReason} icon={BadgeCheck} />
          <ReportInsightCard title="Tänk på" text={primaryTradeoff} icon={ShieldCheck} />
          <ReportInsightCard
            title="Alternativ"
            text={alternative ? `${alternative.name} om prioriteringen skiftar.` : 'Lägg till fler bilar för tydligare alternativ.'}
            icon={ArrowRight}
          />
        </div>
        <div className="reportCompared">
          {compared.map((item) => (
            <div key={item.variant_key} className={item.variant_key === winner.variant_key ? 'isWinner' : ''}>
              <strong>{item.name}</strong>
              <span>{Math.round(item.decision_score)} poäng</span>
              <small>
                {item.price_sek ? formatSEK(item.price_sek) : 'Pris saknas'} · {item.wltp_range_km ? `${item.wltp_range_km} km WLTP` : 'WLTP saknas'}
              </small>
              {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">Källa</a>}
            </div>
          ))}
        </div>
        <button type="button" onClick={onRunReport} disabled={status.state === 'loading'}>
          {status.state === 'loading' ? 'Uppdaterar...' : 'Uppdatera rapport'}
        </button>
        <button type="button" className="secondaryReportAction" onClick={onExportCsv}>Exportera CSV</button>
        {report?.mode === 'local' && <small className="localReportNote">Lokal fallback används när AI-API saknas på statisk hosting.</small>}
        {status.message && <span className={`reportStatus ${status.state}`}>{status.message}</span>}
      </div>
    );
  }
  if (cars.length === 1) {
    return (
      <div className="reportBody">
        <p>
          Du jämför just nu bara <strong>{cars[0].brand} {cars[0].model}</strong>. Lägg till en eller
          två till så blir kontrasten mellan alternativen tydligare.
        </p>
        <button type="button" onClick={onRunReport} disabled={status.state === 'loading'}>
          {status.state === 'loading' ? 'Skapar...' : 'Skapa rapport'}
        </button>
        <button type="button" className="secondaryReportAction" onClick={onExportCsv}>Exportera CSV</button>
        {status.message && <span className={`reportStatus ${status.state}`}>{status.message}</span>}
      </div>
    );
  }
  return (
    <div className="reportBody">
      <p>
        Välj upp till tre bilar och skapa en källbunden rapport. Rapporten hämtas från backend och matchas mot
        publicerade canonical-varianter, inte mot staging- eller review-data.
      </p>
        <button type="button" onClick={onRunReport} disabled={status.state === 'loading'}>
        {status.state === 'loading' ? 'Skapar...' : 'Skapa rapport'}
      </button>
      <button type="button" className="secondaryReportAction" onClick={onExportCsv}>Exportera CSV</button>
      {status.message && <span className={`reportStatus ${status.state}`}>{status.message}</span>}
    </div>
  );
}

function ReportInsightCard({ title, text, icon: Icon }) {
  return (
    <article className="reportInsightCard">
      <span><Icon size={14} /> {title}</span>
      <p>{text}</p>
    </article>
  );
}

function ComparisonTable({ cars }) {
  if (cars.length === 0) {
    return (
      <div className="comparisonEmpty">
        <p>Inga bilar valda för jämförelse än. Klicka på "Jämför" på upp till tre bilar i listan ovan.</p>
      </div>
    );
  }

  const rows = [
    { label: 'Pris från', get: (car) => car.price ? formatSEK(car.price) : 'Ej angivet', value: (car) => car.price, best: 'min' },
    { label: 'WLTP-räckvidd', get: (car) => detailValue(car.rangeVerified, 'km'), value: (car) => car.rangeVerified, best: 'max' },
    { label: 'Snabbladdning', get: (car) => detailValue(car.dcVerified, 'kW'), value: (car) => car.dcVerified, best: 'max' },
    { label: 'Bagage', get: (car) => detailValue(car.cargoVerified, 'liter'), value: (car) => car.cargoVerified, best: 'max' },
    { label: 'Dragvikt', get: (car) => detailValue(car.towingVerified, 'kg'), value: (car) => car.towingVerified, best: 'max' },
    { label: 'Drivlina', get: (car) => car.drivetrain }
  ];

  const gridStyle = {
    gridTemplateColumns: `minmax(10rem, 0.75fr) repeat(${cars.length}, minmax(13rem, 1fr))`,
    minWidth: `${16 + cars.length * 13}rem`
  };

  return (
    <div className="comparisonTable" role="table" aria-label="Jämförelse av elbilar">
      <div className="tableRow tableHead" role="row" style={gridStyle}>
        <span role="columnheader">Mått</span>
        {cars.map((car) => (
          <strong key={car.id} role="columnheader">{car.brand} {car.model}</strong>
        ))}
      </div>
      {rows.map((row) => {
        const numericValues = cars.map(row.value ?? (() => null)).filter((value) => Number.isFinite(value) && value > 0);
        const bestValue = numericValues.length
          ? row.best === 'min' ? Math.min(...numericValues) : Math.max(...numericValues)
          : null;
        return (
        <div className="tableRow" role="row" key={row.label} style={gridStyle}>
          <span role="rowheader">{row.label}</span>
          {cars.map((car) => (
            <strong
              key={`${car.id}-${row.label}`}
              role="cell"
              className={bestValue && row.value?.(car) === bestValue ? 'bestCell' : undefined}
              title={bestValue && row.value?.(car) === bestValue ? `Bästa ${row.best === 'min' ? 'lägsta' : 'högsta'} verifierade värde i jämförelsen.` : undefined}
            >
              {row.get(car)}
            </strong>
          ))}
        </div>
        );
      })}
    </div>
  );
}

function VerificationBadge({ compact = false, date }) {
  return (
    <span className={`verificationBadge ${compact ? 'compact' : ''}`}>
      <BadgeCheck size={compact ? 14 : 16} />
      {compact ? `Verifierad ${date}` : 'Verifierade svenska källor'}
    </span>
  );
}

function ConsumerStep({ icon: Icon = Bot, title, text }) {
  return (
    <article>
      <Icon size={20} />
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}

function PipelineStatusPanel({ status }) {
  const sourceHealth = status?.source_health ?? {};
  const blockerQueues = status?.blocker_queues ?? {};
  const readySources = sourceHealth.ready ?? 0;
  const blockedWork = Object.values(blockerQueues).reduce((sum, value) => sum + Number(value || 0), 0);
  const topBlocker = status?.top_blocker;

  return (
    <div className="pipelineStatusPanel" aria-live="polite">
      <div>
        <span className="eyebrow">Databasstatus</span>
        <h3>{status ? 'Canonical pipeline är aktiv.' : 'Läser pipeline-status...'}</h3>
        <p>
          Publika sidor läser bara publicerade, validerade poster. Osäkra extraktioner hamnar i review
          eller blockeringskö tills källan är kontrollerad.
        </p>
      </div>
      <div className="pipelineMetrics">
        <StatusMetric label="Publika varianter" value={status?.public_variants ?? '...'} />
        <StatusMetric label="I review" value={status?.review_queue_variants ?? '...'} />
        <StatusMetric label="Redo källor" value={readySources} />
        <StatusMetric label="Blockerade jobb" value={blockedWork} />
      </div>
      {topBlocker && (
        <p className="pipelineNext">
          Nästa flaskhals: <strong>{topBlocker.brand} {topBlocker.model}</strong> kräver{' '}
          {topBlocker.priority_reason?.replaceAll('_', ' ') || 'källkontroll'}.
        </p>
      )}
    </div>
  );
}

function StatusMetric({ label, value }) {
  return (
    <div className="statusMetric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function QualityStep({ icon: Icon = HeartHandshake, title, text }) {
  return (
    <article>
      <Icon size={22} />
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}

createRoot(document.getElementById('root')).render(<App />);
