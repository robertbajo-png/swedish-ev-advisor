import React from 'react';
import { ev2VersionGuide } from './ev2-version-guide.js';
import { estimateWinterTripStops, winterTripExample } from './winter-trip.js';

const money = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 1 });
const delta = (value, unit, number = money) => `${value > 0 ? '+' : ''}${number.format(value)} ${unit}`;

export function EV2VersionGuide({ car, cars, appPath }) {
  const versions = ev2VersionGuide(car, cars);
  if (!versions.length) return null;
  return <section className="ev2Guide" id="versionsval" aria-labelledby="ev2-versions-heading">
    <span className="vehicleEyebrow">Köpguide · Kia EV2</span>
    <h2 id="ev2-versions-heading">Vilken version ska jag välja?</h2>
    <p>Se vad varje steg ger för pengarna. Jämförelsen gäller de tre femsitsiga versionerna i katalogen, inte fyrsitsutförandet.</p>
    <div className="ev2GuideGrid">{versions.map(item => <article key={item.car.id} className="ev2GuideCard">
      <h3><a href={appPath('/bilar/' + item.car.id)} aria-current={car.id === item.car.id ? 'page' : undefined}>{item.name}</a></h3>
      <p><strong>{money.format(item.car.price)} kr</strong> · svenskt listpris</p>
      <p>Upp till {item.car.rangeVerified} km WLTP på {item.wheel}-tumshjul · {decimal.format(item.car.batteryVerified)} kWh.</p>
      {item.baseline && <p className="ev2GuideDelta"><strong>Mot {item.baseline}:</strong> {delta(item.priceDifference, 'kr')}, {delta(item.rangeDifference, 'km WLTP')}, {item.batteryDifference ? delta(item.batteryDifference, 'kWh batteri', decimal) : 'samma batterikapacitet'}.</p>}
      <p>{item.use}</p>
      <p className="sectionSource"><a href={item.car.priceSource}>Kias prislista</a> · kontrollerad <time dateTime={item.car.priceVerifiedAt}>{item.car.priceVerifiedAt}</time>{item.car.priceValidUntil && <> · giltig t.o.m. <time dateTime={item.car.priceValidUntil}>{item.car.priceValidUntil}</time></>}</p>
    </article>)}</div>
    <p className="sectionSource"><a href={versions[0].car.source}>Kias svenska tekniska produktfakta</a>. WLTP är inte en garanti för räckvidden i din körning.</p>
    <WinterTripExample versions={versions} />
  </section>;
}

function WinterTripExample({ versions }) {
  const { distanceKm, startFraction, reserveFraction, chargeToFraction, comparisonFactors } = winterTripExample;
  const percent = value => Math.round(value * 100) + ' %';
  return <section className="ev2Winter" aria-labelledby="ev2-winter-heading">
    <h3 id="ev2-winter-heading">Räkneexempel: {distanceKm} km motorväg vintertid</h3>
    <p><strong>Uppskattning, inte ett körtest.</strong> Här jämför vi två antaganden om körsträckan, {percent(comparisonFactors[0])} och {percent(comparisonFactors[1])} av respektive versions WLTP-värde. Procentsatserna är valda för räkneexemplet, inte uppmätta för Kia EV2.</p>
    <p>Start vid {percent(startFraction)}, ankomst och laddstopp vid lägst {percent(reserveFraction)} och laddning till {percent(chargeToFraction)} per stopp. Siffrorna förutsätter laddare där du behöver dem och inkluderar varken kötid eller laddtid.</p>
    <table>
      <caption>Ungefärligt antal laddstopp i räkneexemplet</caption>
      <thead><tr><th scope="col">Version</th>{comparisonFactors.map(factor => <th scope="col" key={factor}>{percent(factor)} av WLTP</th>)}</tr></thead>
      <tbody>{versions.map(item => <tr key={item.car.id}><th scope="row">{item.name}</th>{comparisonFactors.map(factor =>
        <td key={factor}>{estimateWinterTripStops(item.car.rangeVerified, factor) ?? 'Saknas'}</td>)}</tr>)}</tbody>
    </table>
    <p>Planera din faktiska rutt separat. Väder, hastighet, däck, last och batteritemperatur kan ändra både räckvidd och laddtid.</p>
  </section>;
}
