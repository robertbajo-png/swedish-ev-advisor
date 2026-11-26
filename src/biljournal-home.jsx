import React, { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { distanceForWeek } from './ownership-cost.js';

const tripFrequencies = [
  ['once', 'En gång totalt'],
  ['monthly', 'En gång i månaden'],
  ['fortnightly', 'Varannan helg'],
  ['weekly', 'Varje vecka'],
];

export const DEFAULT_WEEK = { commute: '', charge: '', trip: '', cadence: '' };
const EXAMPLE_WEEK = { commute: '32', charge: 'home', trip: '180', cadence: 'monthly' };
const km = new Intl.NumberFormat('sv-SE');

function DistanceField({ id, value, onChange, label }) {
  return <label className="bilRouteField" htmlFor={id}>
    <span>{label}</span>
    <input id={id} type="number" inputMode="numeric" min="0" max="1000" step="1"
      value={value} onChange={event => onChange(event.target.value)} />
  </label>;
}

export function BiljournalWeek({ week, setWeek, onApply }) {
  const [error, setError] = useState('');
  const hasTrip = Number(week.trip) > 0;
  const ready = week.charge && (!hasTrip || week.cadence);
  const distance = ready ? distanceForWeek(week) : null;
  const hasDistance = distance && (distance.annualKm > 0 || distance.onceKm > 0);
  const update = (key, value) => {
    setWeek({ ...week, [key]: value, example: false });
    setError('');
  };

  function submit(event) {
    event.preventDefault();
    if (!hasDistance || distance.annualKm > 60000) {
      setError(!hasDistance ? 'Ange en pendlingssträcka eller en längre resa.' : 'Kalkylen kan räkna på högst 60 000 km per år.');
      return;
    }
    onApply(week);
  }

  return <form className="bilWeek" aria-labelledby="bil-week-title" onSubmit={submit}>
      <header>
        <div><h2 id="bil-week-title" tabIndex={-1}>Din körvecka</h2><p>Sträckan och laddningen följer med till kalkylen.</p></div>
        <button className="bilExampleButton" type="button" onClick={() => { setWeek({...EXAMPLE_WEEK, example: true}); setError(''); }}>Fyll i ett exempel</button>
      </header>
      {week.example && <p className="bilWeekExample" role="status">Exempel ifyllt. Du kan ändra varje värde.</p>}
      <div className="bilWeekRoute">
        <div className="bilRouteStop">
          <h3>Pendling</h3>
          <DistanceField id="bil-commute" value={week.commute} onChange={value => update('commute',value)} label="Km tur och retur per dag" />
          <p>5 dagar i veckan, 46 veckor om året.</p>
        </div>
        <div className="bilRouteStop">
          <h3>Laddning</h3>
          <label className="bilRouteField"><span>Var laddar du oftast?</span>
            <select value={week.charge} onChange={event => update('charge',event.target.value)} required>
              <option value="">Välj laddplats</option><option value="home">Mest hemma (80 %)</option><option value="public">Endast publikt (0 % hemma)</option>
            </select>
          </label>
        </div>
        <div className="bilRouteStop">
          <h3>Helgresa <small>Valfritt</small></h3>
          <div className="bilTripFields">
            <DistanceField id="bil-trip" value={week.trip} onChange={value => update('trip',value)} label="Km tur och retur" />
            <label className="bilRouteField"><span>Hur ofta?</span><select value={week.cadence} onChange={event => update('cadence',event.target.value)} disabled={!hasTrip} required={hasTrip}>
              <option value="">Välj intervall</option>{tripFrequencies.map(([value,label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
          </div>
        </div>
      </div>
      {error && <p role="alert" className="bilWeekError">{error}</p>}
      <div className="bilWeekEnd">
        <p aria-live="polite">{hasDistance && <><strong>{km.format(distance.annualKm)} km/år</strong>{distance.onceKm > 0 && ' + ' + km.format(distance.onceKm) + ' km en gång'}</>}</p>
        <button className="uiPrimary" type="submit">Visa bilurval <ArrowRight size={18} aria-hidden="true" /></button>
      </div>
    </form>;
}
