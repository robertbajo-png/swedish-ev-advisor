import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  ArrowRight,
  BadgeCheck,
  BatteryCharging,
  Bot,
  Calculator,
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
  RotateCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Tag,
  Trees,
  Users,
  WalletCards,
  Zap
} from 'lucide-react';
import { GitCompareArrows, Plus, Weight, X } from 'lucide-react';
import './styles.css';
import { DEFAULT_TCO_ASSUMPTIONS, calculateTco } from './tco.js';
import { NewsPage, NewsArticlePage, NewsPreview, newsJsonLd, useNews } from './news.jsx';
import { publicArticles } from './news-presentation.js';
import { preferredScrollBehavior, revealFocusAboveCompareBar } from './ui-navigation.js';
import { advisorEndpoints } from './api-endpoints.js';
import { ruleAdvice } from './advisor-matching.js';
import { HomePage } from './home.jsx';
import './design-system.css';
import { VehicleCard, VehicleCatalog, ComparisonSelection, vehicleIdentity, vehiclePriceLabel as priceLabel } from './vehicle-ui.jsx';
import './vehicles.css';
import { InfoPage } from './info-pages.jsx';


const formatSEK = (value) =>
  new Intl.NumberFormat('sv-SE', { style: 'currency', currency: 'SEK', maximumFractionDigits: 0 }).format(value);

const formatDecimal = (value) =>
  new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 1 }).format(value);

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
  const consumptionVerified = verifiedNumber(
    row.wltp_consumption_kwh_100km ?? row.consumption_kwh_per_100km ?? row.consumption
  );
  const seats = Number(row.seats) || 5;
  const sourceQuote = row.source_quote || '';
  return {
    id: `${slug(brand)}-${slug(model)}`,
    canonicalKey: `${row.brand}|${row.model}|${row.variant_name}`,
    canonicalModel: row.model,
    variantName,
    brand,
    model,
    body: row.body_type || 'Elbil',
    seats,
    seatsVerified: verifiedNumber(row.seats),
    batteryVerified: verifiedNumber(row.battery_kwh),
    acVerified: verifiedNumber(row.ac_charge_kw),
    price,
    priceType: row.price_type || null,
    priceValidUntil: row.price_valid_until || null,
    range: rangeVerified || 0,
    rangeVerified,
    consumption: consumptionVerified,
    consumptionVerified,
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
    verifiedAt: row.verified_at?.slice(0, 10) || null,
    image: row.image_url || officialImageFor(row.brand, row.model),
    imageSource: row.image_source_url || null,
    marketSeen: row.market_seen,
    availableConfirmed: row.available_confirmed,
    discontinuedCandidate: row.discontinued_candidate,
    comingOrLowVolume: row.coming_or_low_volume,
    summary:
      sourceQuote
        ? `${sourceQuote.slice(0, 170)}${sourceQuote.length > 170 ? '...' : ''}`
        : 'Publicerad med verifierade svenska källor för pris och specifikationer.'
  };
}

async function loadSupabaseCars() {
  if (import.meta.env.VITE_VEHICLE_DATA_MODE !== 'live') return null;
  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !anonKey) return null;
  const response = await fetch(`${supabaseUrl.replace(/\/$/, '')}/rest/v1/public_ev_variants?select=*`, {
    headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` }
  });
  if (!response.ok) throw new Error(`Supabase public view fetch failed: ${response.status}`);
  const rows = await response.json();
  return rows.filter((row) => ['published', 'published_reviewed'].includes(row.validation_status)).map(transformPublicVariant);
}

async function loadLocalPublicCars() {
  const response = await fetch(appPath('/data/public_ev_variants.json'), { cache: 'no-store' });
  if (!response.ok) return null;
  const payload = await response.json();
  const rows = Array.isArray(payload) ? payload : payload.records;
  if (!rows?.length) return null;
  return rows.filter((row) => ['published', 'published_reviewed'].includes(row.validation_status)).map(transformPublicVariant);
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

async function requestAdvisor(advisor) {
  const payload = {
    prompt: advisor.prompt,
    budget: advisor.budget,
    range: advisor.range,
    need: advisor.need,
    explicit_controls: { budget: advisor.budgetExplicit === true, range: advisor.rangeExplicit === true },
  };
  const endpoints = advisorEndpoints('/api/advisor', {
    basePath: import.meta.env.BASE_URL,
    hostname: window.location.hostname,
    development: import.meta.env.DEV
  });
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
  const endpoints = advisorEndpoints('/api/compare', {
    basePath: import.meta.env.BASE_URL,
    hostname: window.location.hostname,
    development: import.meta.env.DEV
  });
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
  const variants = cars.map((car) => ({
    id: car.id, variant_key: car.canonicalKey, brand: car.brand, model: car.canonicalModel, variant_name: car.variantName,
    price_sek: car.price, price_type: car.priceType, price_valid_until: car.priceValidUntil,
    wltp_range_km: car.rangeVerified, dc_charge_kw: car.dcVerified, tow_kg: car.towingVerified,
    boot_liters: car.cargoVerified, seats: car.seatsVerified, drivetrain: car.drivetrain,
    source_url: car.source, source_hash: car.sourceHash, validation_status: car.validationStatus, available_confirmed: car.availableConfirmed,
  }));
  return ruleAdvice(variants, { ...advisor, explicit_controls: { budget: advisor.budgetExplicit === true, range: advisor.rangeExplicit === true } }, { mode: 'local' });
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
  const headers = ['Bil', 'Prisuppgift', 'WLTP km', 'DC kW', 'Dragvikt kg', 'Bagage liter', 'Källa'];
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
  const comparable = cars.filter((item) => item.rangeVerified != null);
  const averageRange = comparable.length > 1 ? Math.round(comparable.reduce((sum, item) => sum + item.rangeVerified, 0) / comparable.length) : null;
  const listPrice = car.price && car.priceType === 'list_price' ? car.price : null;
  return [
    { label: 'Räckvidd per 100 000 kr', value: listPrice && car.rangeVerified ? (car.rangeVerified / (listPrice / 100000)).toFixed(1) + ' km' : 'Uppgift saknas', note: 'Beräknas endast med listpris och WLTP.' },
    { label: 'Pris per WLTP-km', value: listPrice && car.rangeVerified ? Math.round(listPrice / car.rangeVerified).toLocaleString('sv-SE') + ' kr/km' : 'Uppgift saknas', note: 'Listpris fördelat på angiven räckvidd. Inte körkostnad.' },
    { label: 'Räckvidd mot utbudets snitt', value: averageRange != null && car.rangeVerified != null ? (car.rangeVerified >= averageRange ? '+' : '') + (car.rangeVerified - averageRange) + ' km' : 'Uppgift saknas', note: averageRange ? 'Snittet för publicerade varianter med räckviddsuppgift är ' + averageRange + ' km WLTP.' : 'Jämförelseunderlag saknas.' }
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
  if (car.rangeVerified && car.rangeVerified >= advisor.range) reasons.push(`${car.rangeVerified} km WLTP mot ditt mål på ${advisor.range} km`);
  if (car.price && car.price <= advisor.budget) reasons.push(`${priceLabel(car).toLowerCase()} ${formatSEK(car.price)} inom vald budget`);
  if (car.towing >= 1500) reasons.push(`dragvikt upp till ${car.towing} kg`);
  if (advisor.need === 'vinter' && car.drivetrain === 'Fyrhjulsdrift') reasons.push('fyrhjulsdrift för vintervägar');
  if (advisor.need === 'familj' && car.cargo > 450) reasons.push(`${car.cargo} liter lastutrymme`);
  return reasons.slice(0, 3);
}

const defaultFilters = { body: 'Alla', brand: 'Alla', query: '', maxPrice: 750000, minRange: 0, towRequired: false, priceKnown: false, sort: 'match' };
const MAX_COMPARE = 3;
const BASE_URL = (import.meta.env.VITE_SITE_URL || 'https://elbilsagenten.se').replace(/\/$/, '');
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
  if (path === '/jamfor' || path === '/compare') return { type: 'compare' };
  if (path === '/verifiering') return { type: 'verification' };
  if (path === '/kontakt') return { type: 'contact' };
  if (path === '/integritet') return { type: 'privacy' };
  if (path === '/nyheter') return { type: 'news' };
  if (path.startsWith('/nyheter/')) return { type: 'newsArticle', slug: path.split('/').pop() };
  const segment = segments.find((item) => `/${item.slug}` === path);
  if (segment) return { type: 'segment', segment };
  return { type: 'home' };
}

function navigate(path) {
  const nextPath = APP_BASE_PATH ? `${APP_BASE_PATH}${path === '/' ? '' : path}` : path;
  window.history.pushState({}, '', nextPath || '/');
  window.dispatchEvent(new PopStateEvent('popstate'));
  window.scrollTo({ top: 0, behavior: preferredScrollBehavior() });
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

  document.querySelectorAll('script[data-jsonld="page"], script[data-prerender="page"]').forEach((node) => node.remove());
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
    car.rangeVerified != null ? { '@type': 'PropertyValue', name: 'WLTP-räckvidd', value: `${car.rangeVerified} km` } : null,
    car.dcVerified != null ? { '@type': 'PropertyValue', name: 'DC-laddning', value: `${car.dcVerified} kW` } : null,
    car.towingVerified != null ? { '@type': 'PropertyValue', name: 'Dragvikt', value: `${car.towingVerified} kg` } : null,
    car.cargoVerified != null ? { '@type': 'PropertyValue', name: 'Bagage', value: `${car.cargoVerified} liter` } : null
  ].filter(Boolean);
  return {
    '@context': 'https://schema.org',
    '@type': 'Vehicle',
    name: `${car.brand} ${car.model}`,
    brand: { '@type': 'Brand', name: car.brand },
    model: car.model,
    image: car.image || undefined,
    url: `${BASE_URL}/bilar/${car.id}`,
    vehicleSeatingCapacity: car.seatsVerified ?? undefined,
    offers: car.price
      ? {
          '@type': 'Offer',
          price: car.price,
          priceCurrency: 'SEK',
          availability: car.availableConfirmed === true ? 'https://schema.org/InStock' : undefined,
          priceValidUntil: /^\d{4}-\d{2}-\d{2}$/.test(car.priceValidUntil || '') ? car.priceValidUntil : undefined,
          url: `${BASE_URL}/bilar/${car.id}`
        }
      : undefined,
    additionalProperty: properties
  };
}

function App() {
  const [cars, setCars] = useState([]);
  const [dataStatus, setDataStatus] = useState('loading');
  const news = useNews(APP_BASE_PATH);
  const [route, setRoute] = useState(getRoute);
  const contentRef = useRef(null);
  const previousRoute = useRef(route);
  useEffect(() => {
    if (previousRoute.current !== route) contentRef.current?.focus({ preventScroll: true });
    previousRoute.current = route;
  }, [route]);
  const [advisor, setAdvisor] = useState({
    prompt: '',
    budget: 620000,
    range: 520,
    need: 'familj'
  });
  const [advisorResult, setAdvisorResult] = useState(null);
  const [submittedAdvisor, setSubmittedAdvisor] = useState(null);
  const [advisorStatus, setAdvisorStatus] = useState({ state: 'idle', message: '' });
  const [compareReport, setCompareReport] = useState(null);
  const [compareReportStatus, setCompareReportStatus] = useState({ state: 'idle', message: '' });
  const [filters, setFilters] = useState(defaultFilters);
  const [compare, setCompare] = useState([]);
  const compareSelection = compare.join('|');
  const compareSelectionRef = useRef(compareSelection);
  compareSelectionRef.current = compareSelection;
  useEffect(() => {
    setCompareReport(null);
    setCompareReportStatus({ state: 'idle', message: '' });
  }, [compareSelection]);
  const resetFilters = () => setFilters(defaultFilters);

  useEffect(() => {
    const onPopState = () => setRoute(getRoute());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    loadPublicCars()
      .then((result) => {
        if (!result?.cars?.length) { setDataStatus('error'); return; }
        setCars(result.cars);
        setDataStatus('ready');
      })
      .catch((error) => {
        setDataStatus('error');
        console.warn('Published car data unavailable.', error);
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
      .filter((car) => filters.brand === 'Alla' || car.brand === filters.brand)
      .filter((car) => `${car.brand} ${car.model}`.toLocaleLowerCase('sv-SE').includes(filters.query.trim().toLocaleLowerCase('sv-SE')))
      .filter((car) => !car.price || car.price <= filters.maxPrice)
      .filter((car) => car.range >= filters.minRange)
      .filter((car) => !filters.towRequired || car.towing > 0)
      .filter((car) => !filters.priceKnown || !!car.price)
      .sort((a, b) => {
        if (filters.sort === 'price') return (a.price || 9999999) - (b.price || 9999999);
        if (filters.sort === 'range') return b.range - a.range;
        if (filters.sort === 'efficiency') return (a.consumption || 999) - (b.consumption || 999);
        return b.score - a.score;
      });
  }, [cars, effectiveAdvisor, filters, route]);

  const compareCars = compare.map((id) => cars.find((car) => car.id === id)).filter(Boolean);
  const routeCar = route.type === 'car' ? findCarBySlug(cars, route.slug) : null;
  const routeArticle = route.type === 'newsArticle' ? publicArticles(news.articles).find((article) => article.slug === route.slug) : null;

  async function runAdvisor() {
    const query = { ...effectiveAdvisor };
    setSubmittedAdvisor(query);
    setAdvisorStatus({ state: 'loading', message: 'Tolkar dina önskemål och söker passande bilar...' });
    try {
      const result = await requestAdvisor(query);
      setAdvisorResult(result);
      setAdvisorStatus({
        state: 'ready',
        message: result.mode === 'openai' ? 'Dina önskemål är tolkade. Förslagen bygger på verifierade biluppgifter.' : result.interpretation_method === 'form' ? 'Förslag utifrån din valda budget och räckvidd.' : 'Databaserade förslag. AI-tolkning är inte tillgänglig just nu.'
      });
    } catch (error) {
      const candidates = cars.map((car) => ({ ...car, score: scoreCar(car, query) })).sort((a, b) => b.score - a.score);
      setAdvisorResult(localAdvisorResult(query, candidates));
      setAdvisorStatus({
        state: 'ready',
        message: 'AI-rådgivaren är tillfälligt otillgänglig. Här visas databaserade förslag; fritextkrav kan inte tolkas fullt ut.'
      });
    }
  }

  async function runCompareReport() {
    const selection = compareSelection;
    if (!compareCars.length) {
      setCompareReport(buildLocalCompareReport(compareCars));
      setCompareReportStatus({ state: 'error', message: 'Välj minst en bil för att skapa en rapport.' });
      return;
    }
    setCompareReportStatus({ state: 'loading', message: 'Skapar beslutsrapport från verifierade biluppgifter...' });
    try {
      const result = await requestCompareReport(compareCars);
      if (compareSelectionRef.current !== selection) return;
      setCompareReport(result);
      setCompareReportStatus({
        state: 'ready',
        message: result.mode === 'openai' ? 'AI-bedömning baserad på de valda bilarnas uppgifter.' : 'Databaserad bedömning. AI-analys är inte tillgänglig just nu.'
      });
    } catch (error) {
      if (compareSelectionRef.current !== selection) return;
      setCompareReport(null);
      setCompareReportStatus({
        state: 'error',
        message: 'Rapporten kunde inte hämtas. Försök igen. Tabellen, CSV-exporten och kostnadskalkylen fungerar fortfarande.'
      });
    }
  }

  useEffect(() => {
    if (route.type === 'newsArticle') {
      setSeo({
        title: routeArticle ? `${routeArticle.title} | Elbilsagenten` : 'Nyheter | Elbilsagenten',
        description: routeArticle?.intro || 'Nyheter från elbilsvärlden med svenska ögon.',
        jsonLd: routeArticle ? newsJsonLd(routeArticle, BASE_URL) : null
      });
      return;
    }
    if (route.type === 'news') {
      setSeo({ title: 'Elbilsnyheter – modeller, teknik och marknad | Elbilsagenten',
        description: 'Internationella elbilsnyheter med svenska perspektiv, tydliga källor och koppling till ditt nästa bilval.',
        jsonLd: { '@context': 'https://schema.org', '@type': 'CollectionPage', name: 'Elbilsnyheter', url: `${BASE_URL}/nyheter` }
      });
      return;
    }
    if (route.type === 'car') {
      if (routeCar) {
        setSeo({
          title: `${routeCar.brand} ${routeCar.model} – pris, räckvidd och specs | Elbilsagenten`,
          description: `${routeCar.brand} ${routeCar.model}: jämför pris, WLTP-räckvidd, laddning, dragvikt och bagage med verifierade svenska källor.`,
          jsonLd: carJsonLd(routeCar)
        });
        return;
      }
      setSeo({ title: `${dataStatus === 'error' ? 'Biluppgifterna kunde inte hämtas' : dataStatus === 'loading' ? 'Biluppgifter' : 'Bilen hittades inte'} | Elbilsagenten`, description: 'Utforska elbilar, jämför detaljer och hitta en modell som passar dina behov.', jsonLd: null });
      return;
    }
    const routeMetadata = {
      cars: ['Alla elbilar', 'Filtrera elbilar på svenska marknaden efter pris, räckvidd och dina behov.'],
      compare: ['Jämför elbilar', 'Jämför valda elbilar sida vid sida: priser, räckvidd, laddning och uppskattad ägandekostnad.'],
      verification: ['Om våra uppgifter', 'Så använder Elbilsagenten svenska källor och skiljer biluppgifter från antaganden.'],
      contact: ['Kontakt', 'Kontakta ansvarig aktör för Elbilsagenten med frågor, synpunkter och källbelagda rättelser av biluppgifter.'],
      privacy: ['Dina uppgifter', 'Läs hur sökningar hanteras av Elbilsagenten och vilka tjänster som används för bilrådgivning, lagring och drift.'],
    }[route.type];
    if (routeMetadata) {
      setSeo({ title: `${routeMetadata[0]} | Elbilsagenten`, description: routeMetadata[1], jsonLd: null });
      return;
    }
    if (route.type === 'segment') {
      setSeo({
        title: `${route.segment.title} | Elbilsagenten`,
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
      title: 'Elbilsagenten Sverige – hitta rätt elbil med AI',
      description: 'Beskriv budget, körning och behov och få en shortlist med verifierade elbilar, tydliga kompromisser och källor.',
      jsonLd: {
        '@context': 'https://schema.org',
        '@type': 'WebApplication',
        name: 'Elbilsagenten Sverige',
        applicationCategory: 'AutomotiveApplication',
        operatingSystem: 'Web'
      }
    });
  }, [route, routeCar, routeArticle, dataStatus]);

  function toggleCompare(id) {
    setCompare((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (current.length >= MAX_COMPARE) return [...current.slice(1), id];
      return [...current, id];
    });
  }
  const compareLimitReached = compare.length >= MAX_COMPARE;

  return (
    <div className={`appShell page-${route.type} ${compare.length ? 'hasComparison' : ''}`} onFocusCapture={revealFocusAboveCompareBar}>
      <a className="skipLink" href="#main-content" onClick={(event) => { event.preventDefault(); contentRef.current?.focus(); contentRef.current?.scrollIntoView({ behavior: preferredScrollBehavior(), block: 'start' }); }}>Hoppa till innehållet</a>
      <header className={`siteHeader premiumHeader ${route.type === 'car' && routeCar ? 'siteHeaderCinematic' : ''}`}>
        <button className="brand brandButton" type="button" onClick={() => navigate('/')}>
          <span className="brandMark"><Zap size={18} /></span>
          <span>Elbilsagenten</span>
        </button>
        <nav aria-label="Huvudnavigation">
          {[[ '/', 'Hitta elbil', 'home' ], [ '/bilar', 'Alla elbilar', 'cars' ], [ '/jamfor', 'Jämför', 'compare' ], [ '/nyheter', 'Nyheter', 'news' ]].map(([path, label, type]) => <a key={path} href={appPath(path)} aria-current={route.type === type ? 'page' : undefined} onClick={(event) => { if (!event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) { event.preventDefault(); navigate(path); } }}>{label}</a>)}
        </nav>
        <button className="uiPrimary" type="button" onClick={() => {
          if (route.type !== 'home') navigate('/');
          requestAnimationFrame(() => { document.getElementById('home-advisor-query')?.focus(); document.getElementById('hitta-elbil')?.scrollIntoView({ behavior: preferredScrollBehavior() }); });
        }}><Sparkles size={16} /> Fråga AI</button>
      </header>

      <main id="main-content" className="siteMain" ref={contentRef} tabIndex={-1} aria-label="Huvudinnehåll">
      {route.type === 'car' ? (
        dataStatus === 'loading' ? <section className="newsPage"><p role="status">Hämtar bilen...</p></section> : dataStatus === 'error' ? <section className="notFoundPage vehicleContainer"><h1>Biluppgifterna kunde inte hämtas.</h1><p>Försök igen om en stund.</p><button className="uiPrimary" type="button" onClick={() => window.location.reload()}>Försök igen</button></section> : <CarDetailPage
          car={routeCar}
          cars={cars}
          onCompare={toggleCompare}
          selected={routeCar ? compare.includes(routeCar.id) : false}
          compare={compare}
          newsArticles={news.articles}
        />
      ) : (
        <>

      {route.type === 'news' && <NewsPage {...news} navigate={navigate} />}
      {route.type === 'newsArticle' && <NewsArticlePage article={routeArticle} articles={news.articles} loading={news.loading} error={news.error} navigate={navigate} cars={cars} renderVehicleCard={(car) => <VehicleCard car={car} selected={compare.includes(car.id)} onCompare={toggleCompare} navigate={navigate} appPath={appPath} renderImage={(item) => <CarImage key={item.id} car={item} />} />} />}

      {route.type === 'home' && (
        <HomePage
          cars={cars}
          dataStatus={dataStatus}
          advisor={effectiveAdvisor}
          setAdvisor={setAdvisor}
          result={advisorResult}
          status={advisorStatus}
          submittedAdvisor={submittedAdvisor}
          onSubmit={runAdvisor}
          compare={compare}
          onCompare={toggleCompare}
          navigate={navigate}
          appPath={appPath}
          renderImage={(car, priority = false) => <CarImage key={car.id} car={car} priority={priority} />}
          newsPreview={<NewsPreview articles={news.articles} navigate={navigate} loading={news.loading} error={news.error} showEmpty />}
        />
      )}

      {route.type === 'verification' && <VerificationPage />}
      {['contact', 'privacy'].includes(route.type) && <InfoPage type={route.type} />}
      {['cars', 'segment'].includes(route.type) && <VehicleCatalog
        cars={cars} ranked={ranked} filters={filters} setFilters={setFilters}
        resetFilters={resetFilters} dataStatus={dataStatus} segment={route.segment}
        compare={compare} onCompare={toggleCompare} navigate={navigate} appPath={appPath}
        renderFilters={(prefix, brands) => <FilterSidebar prefix={prefix} brands={brands} bodies={[...new Set(cars.map((car) => car.body).filter((body) => body !== 'Elbil'))]} filters={filters} setFilters={setFilters} resultCount={ranked.length} totalCount={cars.length} onReset={resetFilters} />}
        renderCard={(car) => <CarCard key={car.id} headingLevel={2} car={car} selected={compare.includes(car.id)} onCompare={() => toggleCompare(car.id)} compareLimitReached={!compare.includes(car.id) && compareLimitReached} />}
      />}
      {route.type === 'compare' && <section className="compareSection vehicleCompare vehicleContainer" id="compare">
        <div className="vehiclePageIntro"><span className="vehicleEyebrow">Ditt beslutsunderlag</span><h1>Jämför sida vid sida</h1><p>Vilken passar dig bäst? Se skillnaderna i pris, räckvidd och livet med bilen.</p></div>
        <ComparisonSelection cars={compareCars} allCars={cars} onCompare={toggleCompare} renderImage={(car) => <CarImage key={car.id} car={car} />} navigate={navigate} appPath={appPath} />
        {!!compareCars.length && <>
          <div className="comparisonReport">
            <div><span className="vehicleEyebrow"><Sparkles size={16} /> Rådgivning</span><h2>Styrkor, skillnader och kompromisser.</h2><p>Rapportens bedömning är generell. Ditt bilval beror på vilka behov du prioriterar.</p><button className="homeTextLink" type="button" onClick={() => navigate('/')}>Hitta bil utifrån mina behov <ArrowRight size={16} /></button></div>
            <div className="reportCard"><RecommendationText cars={compareCars} report={compareReport} status={compareReportStatus} onRunReport={runCompareReport} onExportCsv={() => exportCompareCsv(compareCars)} /></div>
          </div>
          <section className="comparisonFacts" aria-labelledby="comparison-facts-title"><div className="vehicleSectionHeading"><span className="vehicleEyebrow">Detaljerna som gör skillnad</span><h2 id="comparison-facts-title">Fakta sida vid sida.</h2></div><ComparisonTable cars={compareCars} /></section>
          <OwnershipCostCalculator cars={compareCars} />
        </>}
      </section>}

      </>
      )}
      </main>

      {!['car', 'compare', 'news', 'newsArticle', 'verification', 'contact', 'privacy'].includes(route.type) && <CompareBar cars={compareCars} onRemove={toggleCompare} onClear={() => setCompare([])} />}
      <footer>
        <span><Zap size={16} /> Elbilsagenten · Ditt nästa bilval.</span>
        <div>{[['/kontakt', 'Kontakt'], ['/integritet', 'Dina uppgifter'], ['/verifiering', 'Om våra uppgifter']].map(([path, label]) => <a key={path} href={appPath(path)} onClick={(event) => { if (!event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) { event.preventDefault(); navigate(path); } }}>{label}</a>)}<button type="button" onClick={() => { window.scrollTo({ top: 0, behavior: preferredScrollBehavior() }); document.querySelector('.brandButton')?.focus({ preventScroll: true }); }}><Home size={16} /> Till toppen</button></div>
      </footer>
    </div>
  );
}


function FilterSidebar({ filters, setFilters, resultCount, totalCount, onReset, prefix = 'catalog', brands = [], bodies = [] }) {
  const update = (key, value) => setFilters({ ...filters, [key]: value });
  return <aside className="filterSidebar vehicleFilters" aria-label="Bilfilter">
    <div className="filterTitle"><SlidersHorizontal size={17} /> Anpassa urvalet<button type="button" onClick={onReset}>Återställ</button></div>
    <label htmlFor={prefix + '-brand'}>Märke</label>
    <select id={prefix + '-brand'} value={filters.brand} onChange={(event) => update('brand', event.target.value)}><option>Alla</option>{brands.map((brand) => <option key={brand}>{brand}</option>)}</select>
    <label htmlFor={prefix + '-body'}>Kaross</label>
    <select id={prefix + '-body'} value={filters.body} onChange={(event) => update('body', event.target.value)}><option>Alla</option>{bodies.map((body) => <option key={body}>{body}</option>)}</select>
    <div className="vehicleFilterRange"><label htmlFor={prefix + '-price'}>Maxpris</label><output htmlFor={prefix + '-price'}>{formatSEK(filters.maxPrice)}</output><input id={prefix + '-price'} type="range" min="100000" max="1200000" step="10000" value={filters.maxPrice} onChange={(event) => update('maxPrice', Number(event.target.value))} /></div>
    <div className="vehicleFilterRange"><label htmlFor={prefix + '-range'}>Minsta räckvidd</label><output htmlFor={prefix + '-range'}>{filters.minRange ? filters.minRange + ' km' : 'Alla räckvidder'}</output><input id={prefix + '-range'} type="range" min="0" max="1000" step="20" value={filters.minRange} onChange={(event) => update('minRange', Number(event.target.value))} /></div>
    <div className="filterToggles"><label><input type="checkbox" checked={filters.towRequired} onChange={(event) => update('towRequired', event.target.checked)} /> Dragvikt angiven</label><label><input type="checkbox" checked={filters.priceKnown} onChange={(event) => update('priceKnown', event.target.checked)} /> Pris angivet</label></div>
    <p className="vehicleFilterNote">{resultCount} av {totalCount} varianter</p>
  </aside>;
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

function CarCard({ car, selected, onCompare, compareLimitReached, headingLevel = 3 }) {
  return <VehicleCard className="carCard" car={car} selected={selected} headingLevel={headingLevel} compareLimitReached={compareLimitReached}
    onCompare={onCompare} navigate={navigate} appPath={appPath} renderImage={(item) => <CarImage key={item.id} car={item} />} />;
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

function VerificationPage() {
  return (
    <section className="verificationPage">
      <div className="sectionIntro wide">
        <span className="eyebrow">Verifiering</span>
        <h1>Så kan du lita mer på uppgifterna.</h1>
        <p>
          Elbilsagenten visar biluppgifter med svenska källor och markerar tydligt när något saknas.
          Målet är att hjälpa dig jämföra utan att blanda ihop säkra uppgifter med antaganden.
        </p>
      </div>
      <div className="verificationGrid">
        <QualityStep icon={CarFront} title="Svensk marknad" text="Vi prioriterar elbilar som är relevanta för svenska köpare och registreras eller säljs här." />
        <QualityStep icon={ShieldCheck} title="Officiella källor" text="Pris, räckvidd, laddning, bagage och dragvikt kontrolleras mot tillverkare eller importör när uppgiften finns." />
        <QualityStep icon={Sparkles} title="AI med kontroll" text="AI kan hjälpa till att läsa källor, men osäkra eller ofullständiga värden visas inte som fakta." />
        <QualityStep icon={BadgeCheck} title="Saknas betyder saknas" text="Om ett fält saknar säker uppgift visar vi “Uppgift saknas” i stället för en missvisande nolla." />
      </div>
      <article className="verificationNote">
        <h2>Om priser</h2>
        <p>
          Om pris saknas betyder det att vi inte har ett säkert officiellt svenskt pris för just den versionen.
          Tillfälliga kampanjer och ordinarie listpris bör hållas isär.
        </p>
      </article>
    </section>
  );
}

function CarDetailPage({ car, cars, onCompare, selected, compare = [], newsArticles = [] }) {
  if (!car) return <section className="notFoundPage vehicleContainer"><h1>Bilen hittades inte.</h1><p>Välj en annan modell i bilguiden.</p><button className="uiPrimary" onClick={() => navigate('/bilar')}>Visa alla bilar</button></section>;
  const identity = vehicleIdentity(car);
  const alternatives = cars.filter((item) => item.canonicalKey?.split('|').slice(0, 2).join('|') !== car.canonicalKey?.split('|').slice(0, 2).join('|'));
  const similarCars = [...alternatives.filter((item) => car.price && item.price && Math.abs(item.price - car.price) < 120000), ...alternatives];
  const distinct = [...new Map(similarCars.map((item) => [item.brand + '|' + item.canonicalModel, item])).values()].slice(0, 3);
  return <div className="vehicleDetail">
    <section className="vehicleDetailHero" aria-labelledby="vehicle-title">
      <div className="vehicleHeroMedia"><CarImage key={car.id} car={car} priority /></div>
      <div className="vehicleHeroOverlay" />
      <div className="vehicleHeroCopy vehicleContainer">
        <a className="vehicleBackLink" href={appPath('/bilar')} onClick={(event) => { if (!event.ctrlKey && !event.metaKey) { event.preventDefault(); navigate('/bilar'); } }}>Alla elbilar <ArrowRight size={15} /></a>
        <span className="vehicleHeroSource"><BadgeCheck size={15} /> Uppgifter med svenska källor</span>
        <h1 id="vehicle-title">{car.brand} {identity.model}<span>{identity.variant}</span></h1>
        <p className="vehicleHeroDescription">{car.rangeVerified != null ? car.rangeVerified + ' km räckvidd enligt WLTP. ' : ''}{car.dcVerified != null ? 'DC-laddning upp till ' + car.dcVerified + ' kW. ' : ''}Utforska detaljerna och jämför med dina alternativ.</p>
        <MarketStatusBadges car={car} />
        <div className="vehicleHeroActions"><button className="uiPrimary" type="button" aria-pressed={selected} onClick={() => onCompare(car.id)}>{selected ? <Check size={17} /> : <Plus size={17} />}{selected ? 'Tillagd i jämförelse' : 'Lägg till i jämförelse'}</button><a href={car.source} target="_blank" rel="noreferrer">Öppna källa <ExternalLink size={16} /></a>{selected && <button className="vehicleHeroCompareLink" type="button" onClick={() => navigate('/jamfor')}>Jämför nu <ArrowRight size={16} /></button>}</div>
      </div>
      <div className="vehicleHeroStats vehicleContainer">{[[Tag, priceLabel(car), car.price ? formatSEK(car.price) : 'Ej angivet'], [Route, 'WLTP-räckvidd', detailValue(car.rangeVerified, 'km')], [PlugZap, 'DC-laddning', detailValue(car.dcVerified, 'kW')], [Weight, 'Dragvikt', detailValue(car.towingVerified, 'kg')]].map(([Icon, label, value]) => <div key={label}><Icon size={20} aria-hidden="true" /><span>{label}</span><strong>{value}</strong></div>)}</div>
    </section>
    <nav className="vehicleDetailNav vehicleContainer" aria-label="På bilsidan"><a href="#bilprofil">Överblick</a><a href="#specifikationer">Specifikationer</a><a href="#nyckeltal">Nyckeltal</a><a href="#bilkallor">Källor</a></nav>
    <div className="vehicleDetailBody vehicleContainer">
      <AiSummaryCard car={car} />
      <section className="detailSectionGrid" id="specifikationer" aria-label="Detaljerade specifikationer">
        <DetailInfoCard eyebrow="Drivlina" title="Grunden i bilen" source={car.source} verifiedAt={car.verifiedAt} items={[[priceLabel(car), car.price ? formatSEK(car.price) : 'Ej angivet'], ['Säten', detailValue(car.seatsVerified)], ['Drivning', car.drivetrain === 'Ej verifierad' ? 'Uppgift saknas' : car.drivetrain], ['Kaross', car.body === 'Elbil' ? 'Uppgift saknas' : car.body]]} />
        <DetailInfoCard eyebrow="Räckvidd och laddning" title="Energi i vardagen" source={car.source} verifiedAt={car.verifiedAt} items={[[ 'WLTP-räckvidd', detailValue(car.rangeVerified, 'km')], ['Batteri', detailValue(car.batteryVerified, 'kWh')], ['DC-laddning', detailValue(car.dcVerified, 'kW')], ['AC-laddning', detailValue(car.acVerified, 'kW')], ['Förbrukning', car.consumptionVerified != null ? formatDecimal(car.consumptionVerified) + ' kWh/100 km' : 'Uppgift saknas']]} />
        <DetailInfoCard eyebrow="Praktikalitet" title="Plats för ditt liv" source={car.source} verifiedAt={car.verifiedAt} items={[[ 'Dragvikt', detailValue(car.towingVerified, 'kg')], ['Bagage', detailValue(car.cargoVerified, 'liter')], ['Säten', detailValue(car.seatsVerified)]]} />
      </section>
      <div id="nyckeltal"><DecisionMetricsCard car={car} cars={cars} /></div>
      <SourceVerificationCard car={car} />
    </div>
    <NewsPreview articles={newsArticles} navigate={navigate} title="Senaste nytt om denna bil" relatedKey={car.canonicalKey?.split('|').slice(0, 2).join('|')} />
    <section className="vehicleSimilar vehicleContainer"><div className="vehicleSectionHeading"><span className="vehicleEyebrow">Fler perspektiv</span><h2>Andra elbilar att jämföra.</h2></div><div className="vehicleCardGrid">{distinct.map((item) => <CarCard key={item.id} car={item} selected={compare.includes(item.id)} onCompare={() => onCompare(item.id)} compareLimitReached={compare.length >= 3 && !compare.includes(item.id)} />)}</div></section>
  </div>;
}

function AiSummaryCard({ car }) {
  const strengths = [car.rangeVerified != null ? car.rangeVerified + ' km räckvidd enligt WLTP.' : null, car.dcVerified != null ? 'DC-laddning upp till ' + car.dcVerified + ' kW.' : null, car.towingVerified != null ? 'Angiven dragvikt: ' + car.towingVerified + ' kg.' : null].filter(Boolean);
  const missing = [[car.price, 'svenskt pris'], [car.dcVerified, 'DC-laddning'], [car.towingVerified, 'dragvikt']].filter(([value]) => value == null).map(([, label]) => label);
  const suitability = [car.rangeVerified >= 500 ? 'För dig som prioriterar lång angiven räckvidd.' : null, car.towingVerified >= 1500 ? 'För dig som behöver dra ett tyngre släp.' : null, car.cargoVerified >= 450 ? 'För dig som behöver större bagageutrymme.' : null].filter(Boolean);
  return <section className="vehicleAssessment" id="bilprofil"><div><span className="vehicleEyebrow">Bilens profil</span><h2>Det här är bra att veta.</h2><p>Databaserad sammanfattning av bilens uppgifter, inte ett körtest.</p></div><div className="vehicleAssessmentColumns"><SummaryBlock title="Passar dig som" items={suitability.length ? suitability : ['Se specifikationerna mot dina egna behov.']} /><SummaryBlock title="Några nyckelfakta" items={strengths.length ? strengths : ['Uppgift saknas i databasen.']} /><SummaryBlock title="Att väga in" items={[...(!car.availableConfirmed ? ['Aktuell tillgänglighet är inte separat bekräftad.'] : []), ...(missing.length ? ['Uppgifter saknas om ' + missing.join(', ') + '.'] : ['WLTP är ett standardiserat mätvärde, inte en garanti för din körning.'])]} /></div></section>;
}

function DecisionMetricsCard({ car, cars }) {
  return (
    <section className="decisionMetricsCard">
      <div>
        <span className="eyebrow">Beslutsnyckeltal</span>
        <h2>Nyckeltal för ditt bilval.</h2>
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
  return <section className="vehicleSources" id="bilkallor"><details><summary><BadgeCheck size={18} /><span>Källor och uppdateringar</span><Plus size={17} /></summary><div><a href={car.source} target="_blank" rel="noreferrer">Öppna bilens faktakälla <ExternalLink size={15} /></a><p>{car.verifiedAt ? 'Senast verifierad ' + car.verifiedAt + '.' : 'Verifieringsdatum saknas i underlaget.'}</p><MarketStatusBadges car={car} /><p>Saknade uppgifter markeras öppet. Marknadsnärvaro innebär inte automatiskt att bilen går att beställa.</p></div></details></section>;
}

function CarImage({ car, priority = false }) {
  const [failedImage, setFailedImage] = useState(null);
  if (car?.image && failedImage !== car.image) {
    return <img src={car.image} alt={`${car.brand} ${car.model}`} loading={priority ? 'eager' : 'lazy'} fetchPriority={priority ? 'high' : 'auto'} decoding="async" onError={() => setFailedImage(car.image)} />;
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
    <div className={`metricItem ${missing ? 'isMissing' : ''}`} title={missing ? 'Tillverkaren/importören har inte ett verifierat publicerat värde för detta fält.' : undefined}>
      {Icon && <Icon size={20} aria-hidden="true" />}
      <span>{label}</span>
      <strong>{value}</strong>
      {missing && <small>Ej verifierat</small>}
    </div>
  );
}

function CompareBar({ cars, onRemove, onClear }) {
  useLayoutEffect(() => {
    if (cars.length) revealFocusAboveCompareBar({ target: document.activeElement });
  }, [cars.length]);
  if (!cars.length) return null;
  return <aside className="vehicleCompareBar" aria-label="Din jämförelse"><strong><GitCompareArrows size={18} /> {cars.length} av {MAX_COMPARE}</strong><div className="vehicleCompareChips">{cars.map((car) => <button key={car.id} type="button" onClick={() => onRemove(car.id)} aria-label={'Ta bort ' + car.brand + ' ' + car.model}><span>{car.brand} {car.model}</span><X size={14} /></button>)}</div><button className="vehicleCompareClear" type="button" onClick={onClear} aria-label="Rensa jämförelse" title="Rensa jämförelse"><RotateCcw size={16} /></button><button className="uiPrimary" type="button" onClick={() => navigate('/jamfor')}>Jämför <ArrowRight size={16} /></button></aside>;
}

function RecommendationText({ cars, report, status, onRunReport, onExportCsv }) {
  if (cars.length === 0) {
    return <p>Välj upp till tre bilar i listan ovan så sammanfattar vi kompromisserna här.</p>;
  }
  if (report?.winner) {
    const winner = report.winner;
    const compared = report.compared ?? [];
    const alternative = compared.find((item) => item.variant_key !== winner.variant_key);
    const primaryReason = report.reasons?.[0] ?? 'Starkast helhetsbalans i jämförelsen.';
    const primaryTradeoff = report.tradeoffs?.[0] ?? 'Kontrollera detaljerna mot dina egna krav innan beslut.';

    return (
      <div className="reportBody">
        <div className="reportWinner">
          <span><Sparkles size={14} /> Högst i rapportens viktning</span>
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
        Välj upp till tre bilar och skapa en rapport med styrkor, kompromisser och tydliga källor.
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

const TCO_COMPONENTS = [
  ['Värdeminskning', 'depreciationSek', '#245e5b'],
  ['Finansiering', 'financingSek', '#647b8b'],
  ['Laddning', 'electricitySek', '#a7c8b8'],
  ['Försäkring', 'insuranceSek', '#bba06e'],
  ['Service & skatt', 'serviceAndTaxSek', '#ce7668'],
];

function OwnershipCostCalculator({ cars }) {
  const [assumptions, setAssumptions] = useState({ ...DEFAULT_TCO_ASSUMPTIONS });
  const results = useMemo(
    () => cars.map((car) => ({ car, result: calculateTco(car, assumptions) })),
    [cars, assumptions]
  );
  const calculable = results.filter(({ result }) => result.calculable);
  const bestMonthly = calculable.length ? Math.min(...calculable.map(({ result }) => result.monthlySek)) : null;

  function updateAssumption(key, value) {
    setAssumptions((current) => ({ ...current, [key]: Number(value) }));
  }

  return (
    <section className="tcoCalculator" aria-labelledby="tco-title">
      <div className="tcoHeader">
        <div>
          <span className="eyebrow"><Calculator size={15} /> Ägandekostnad</span>
          <h2 id="tco-title">Vad kostar bilen för dig?</h2>
          <p>Jämför uppskattad kostnad per månad. Bilpriset kommer från respektive källa; övriga värden är dina justerbara antaganden.</p>
        </div>
        <button
          className="tcoReset"
          type="button"
          onClick={() => setAssumptions({ ...DEFAULT_TCO_ASSUMPTIONS })}
          title="Återställ antaganden"
          aria-label="Återställ antaganden"
        >
          <RotateCcw size={18} />
        </button>
      </div>

      <div className="tcoLayout">
        <div className="tcoControls">
          <TcoRange
            label="Körsträcka per år"
            value={assumptions.annualKm}
            min={5000}
            max={50000}
            step={1000}
            display={`${new Intl.NumberFormat('sv-SE').format(assumptions.annualKm)} km`}
            onChange={(value) => updateAssumption('annualKm', value)}
          />
          <TcoRange
            label="Ägandetid"
            value={assumptions.years}
            min={2}
            max={8}
            step={1}
            display={`${assumptions.years} år`}
            onChange={(value) => updateAssumption('years', value)}
          />
          <TcoRange
            label="Laddning hemma"
            value={assumptions.homeChargingPercent}
            min={0}
            max={100}
            step={10}
            display={`${assumptions.homeChargingPercent} %`}
            onChange={(value) => updateAssumption('homeChargingPercent', value)}
          />
          <TcoRange
            label="Beräknat restvärde"
            value={assumptions.residualPercent}
            min={20}
            max={70}
            step={5}
            display={`${assumptions.residualPercent} %`}
            onChange={(value) => updateAssumption('residualPercent', value)}
          />
          <TcoRange
            label="Ränta"
            value={assumptions.annualInterestPercent}
            min={0}
            max={12}
            step={0.5}
            display={`${String(assumptions.annualInterestPercent).replace('.', ',')} %`}
            onChange={(value) => updateAssumption('annualInterestPercent', value)}
          />
          <TcoRange
            label="Antagen förbrukning"
            value={assumptions.assumedConsumptionKwh100Km}
            min={10}
            max={35}
            step={1}
            display={`${assumptions.assumedConsumptionKwh100Km} kWh/100 km`}
            onChange={(value) => updateAssumption('assumedConsumptionKwh100Km', value)}
          />

          <details className="tcoAdvanced">
            <summary>Elpris och övriga kostnader</summary>
            <div>
              <TcoNumberInput label="El hemma" value={assumptions.homeElectricitySekKwh} unit="kr/kWh" step={0.1} onChange={(value) => updateAssumption('homeElectricitySekKwh', value)} />
              <TcoNumberInput label="Publik laddning" value={assumptions.publicElectricitySekKwh} unit="kr/kWh" step={0.1} onChange={(value) => updateAssumption('publicElectricitySekKwh', value)} />
              <TcoNumberInput label="Försäkring" value={assumptions.insuranceSekMonth} unit="kr/mån" step={50} onChange={(value) => updateAssumption('insuranceSekMonth', value)} />
              <TcoNumberInput label="Service" value={assumptions.serviceSekYear} unit="kr/år" step={500} onChange={(value) => updateAssumption('serviceSekYear', value)} />
              <TcoNumberInput label="Fordonsskatt" value={assumptions.taxSekYear} unit="kr/år" step={10} onChange={(value) => updateAssumption('taxSekYear', value)} />
            </div>
          </details>
        </div>

        <div className="tcoResults" aria-live="polite">
          {results.length === 0 ? (
            <div className="tcoEmpty">
              <WalletCards size={24} />
              <strong>Välj bilar för att beräkna kostnaden.</strong>
              <p>Lägg till upp till tre bilar från bilsidan.</p>
            </div>
          ) : results.map(({ car, result }) => (
            <TcoResultCard
              key={car.id}
              car={car}
              result={result}
              isBest={result.calculable && result.monthlySek === bestMonthly && calculable.length > 1}
            />
          ))}
        </div>
      </div>

      <div className="tcoDisclosure">
        <BadgeCheck size={16} />
        <span>Pris hämtas från bilens angivna källa. Kalkylen är en uppskattning och inkluderar inte kontantinsatsens alternativkostnad, parkering eller laddbox.</span>
      </div>
    </section>
  );
}

function TcoRange({ label, value, min, max, step, display, onChange }) {
  return (
    <label className="tcoRange">
      <span>{label}<strong>{display}</strong></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function TcoNumberInput({ label, value, unit, step, onChange }) {
  return (
    <label className="tcoNumberInput">
      <span>{label}</span>
      <div>
        <input type="number" min="0" step={step} value={value} onChange={(event) => onChange(event.target.value)} />
        <small>{unit}</small>
      </div>
    </label>
  );
}

function TcoResultCard({ car, result, isBest }) {
  if (!result.calculable) {
    return (
      <article className="tcoResultCard isMissing">
        <span>{car.brand}</span>
        <h3>{car.model}</h3>
        <div className="tcoMissingPrice">
          <WalletCards size={22} />
          <strong>Pris saknas</strong>
          <p>Ägandekostnaden kan inte beräknas utan ett publicerat svenskt pris.</p>
        </div>
        {car.source && <a href={car.source} target="_blank" rel="noreferrer">Öppna bilens källa <ExternalLink size={14} /></a>}
      </article>
    );
  }

  const breakdown = {
    ...result.components,
    serviceAndTaxSek: result.components.serviceSek + result.components.taxSek,
  };

  return (
    <article className={`tcoResultCard ${isBest ? 'isBest' : ''}`}>
      <div className="tcoResultHeading">
        <div><span>{car.brand}</span><h3>{car.model}</h3></div>
        {isBest && <strong className="tcoBestBadge">Lägst beräknad kostnad</strong>}
      </div>
      <div className="tcoPrimaryValue">
        <strong>{formatSEK(Math.round(result.monthlySek))}</strong>
        <span>per månad</span>
      </div>
      <div className="tcoSecondaryValues">
        <div><span>Total {result.assumptions.years} år</span><strong>{formatSEK(Math.round(result.totalSek))}</strong></div>
        <div><span>Kostnad per mil</span><strong>{formatSEK(Math.round(result.costPerKmSek * 10))}</strong></div>
      </div>
      <div className="tcoStack" aria-label="Kostnadsfördelning">
        {TCO_COMPONENTS.map(([label, key, color]) => {
          const value = breakdown[key];
          return <span key={key} style={{ width: `${(value / result.totalSek) * 100}%`, backgroundColor: color }} title={`${label}: ${formatSEK(Math.round(value))}`} />;
        })}
      </div>
      <div className="tcoLegend">
        {TCO_COMPONENTS.map(([label, key, color]) => (
          <span key={key}><i style={{ backgroundColor: color }} />{label}</span>
        ))}
      </div>
      <p className="tcoConsumptionNote">
        <BatteryCharging size={15} /> {formatDecimal(result.consumptionKwh100Km)} kWh/100 km
        <small>{result.consumptionSource === 'verified' ? 'Verifierad biluppgift' : 'Antagande'}</small>
      </p>
    </article>
  );
}

function ComparisonTable({ cars }) {
  if (!cars.length) return null;
  const valueMetric = (field) => (car) => car[field];
  const rows = [
    { label: 'Pris', get: (car) => car.price ? priceLabel(car) + ': ' + formatSEK(car.price) : 'Ej angivet', value: valueMetric('price'), best: 'min', comparable: cars.every((car) => car.priceType) && new Set(cars.map((car) => car.priceType)).size === 1 },
    { label: 'WLTP-räckvidd', get: (car) => detailValue(car.rangeVerified, 'km'), value: valueMetric('rangeVerified'), best: 'max' },
    { label: 'Batteri', get: (car) => detailValue(car.batteryVerified, 'kWh') },
    { label: 'DC-laddning', get: (car) => detailValue(car.dcVerified, 'kW'), value: valueMetric('dcVerified'), best: 'max' },
    { label: 'AC-laddning', get: (car) => detailValue(car.acVerified, 'kW') },
    { label: 'Förbrukning WLTP', get: (car) => car.consumptionVerified != null ? formatDecimal(car.consumptionVerified) + ' kWh/100 km' : 'Uppgift saknas', value: valueMetric('consumptionVerified'), best: 'min' },
    { label: 'Bagage', get: (car) => detailValue(car.cargoVerified, 'liter'), value: valueMetric('cargoVerified'), best: 'max' },
    { label: 'Dragvikt', get: (car) => detailValue(car.towingVerified, 'kg'), value: valueMetric('towingVerified'), best: 'max' },
    { label: 'Säten', get: (car) => detailValue(car.seatsVerified) },
    { label: 'Drivning', get: (car) => car.drivetrain === 'Ej verifierad' ? 'Uppgift saknas' : car.drivetrain },
    { label: 'Räckvidd per 100 000 kr', get: (car) => car.price && car.priceType === 'list_price' && car.rangeVerified ? Math.round(car.rangeVerified / (car.price / 100000)) + ' km' : 'Uppgift saknas' }
  ];
  return <div className="comparisonTable" tabIndex={0} role="region" aria-label="Jämförelse av elbilar, rulla i sidled">
    <table style={{ minWidth: 190 + cars.length * 240 }}><caption>Valda varianter och deras uppgifter</caption>
      <thead><tr><th scope="col">Egenskap</th>{cars.map((car) => <th scope="col" key={car.id}>{car.brand} {car.model}</th>)}</tr></thead>
      <tbody>{rows.map((row) => {
        const values = cars.map(row.value || (() => null)).filter((value) => Number.isFinite(value));
        const meaningful = row.best && row.comparable !== false && values.length > 1 && Math.min(...values) !== Math.max(...values);
        const best = meaningful ? (row.best === 'min' ? Math.min(...values) : Math.max(...values)) : null;
        return <tr key={row.label}><th scope="row">{row.label}</th>{cars.map((car) => {
          const highlighted = best !== null && row.value(car) === best;
          const tip = highlighted ? (row.best === 'min' ? 'Lägst' : 'Högst') + ' angivet värde bland de valda bilarna med denna uppgift. Saknade uppgifter är inte medräknade.' : undefined;
          return <td key={car.id} className={highlighted ? 'bestCell' : undefined} title={tip}><span>{row.get(car)}{highlighted && <Check size={14} aria-hidden="true" />}</span></td>;
        })}</tr>;
      })}<tr><th scope="row">Källa</th>{cars.map((car) => <td key={car.id}><a href={car.source} target="_blank" rel="noreferrer">Bilens faktakälla <ExternalLink size={13} /></a>{car.verifiedAt && <small>Verifierad {car.verifiedAt}</small>}</td>)}</tr></tbody>
    </table>
  </div>;
}

function VerificationBadge({ compact = false, date }) {
  return (
        <span className={`verificationBadge ${compact ? 'compact' : ''}`}>
      <BadgeCheck size={compact ? 14 : 16} />
      {compact ? (date ? `Verifierad ${date}` : 'Källa finns') : 'Verifierade svenska källor'}
    </span>
  );
}


function QualityStep({ icon: Icon = HeartHandshake, title, text }) {
  return (
    <article>
      <Icon size={22} />
      <h2>{title}</h2>
      <p>{text}</p>
    </article>
  );
}

createRoot(document.getElementById('root')).render(<App />);
