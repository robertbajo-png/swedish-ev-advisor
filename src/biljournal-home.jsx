
import React from 'react';
import { coverPhoto } from './biljournal-images.js';
import { assetPath } from './preview-paths.js';

const routeChoices = {
  commute: [['16','16 km/dag'],['32','32 km/dag'],['64','64 km/dag']],
  charge: [['home','Hemma'],['public','Publikt']],
  trip: [['90','90 km'],['180','180 km'],['320','320 km']],
  cadence: [['once','En gång totalt'],['monthly','Varje månad'],['weekly','Varje vecka']],
};
export const DEFAULT_WEEK = { commute: '32', charge: 'home', trip: '180', cadence: 'monthly' };

function RouteField({ name, label, week, setWeek }) {
  return <fieldset className="bilWeekChoices"><legend>{label}</legend>
    {routeChoices[name].map(([value,text]) => <label key={value}><input type="radio" name={name} value={value} checked={week[name] === value} onChange={() => setWeek({ ...week, [name]: value })} /> {text}</label>)}
  </fieldset>;
}

export function BiljournalWeek({ week, setWeek, onApply }) {
  const display = (key) => routeChoices[key].find(([id]) => id === week[key])[1];
  return <>
    <section className="bilCover" aria-labelledby="bil-cover-title">
      <div className="bilWidth bilCoverGrid">
        <div className="bilCoverText"><h1 id="bil-cover-title">Din körvecka</h1><p>Hitta en elbil för dina resor. Räkna på vad den kostar att äga.</p></div>
        <figure className="bilCoverPhoto"><img src={assetPath(coverPhoto)} width="800" height="474" alt="Hyundai Inster Prime parkerad, sedd snett framifrån" fetchPriority="high" /><figcaption>Hyundai Inster Prime</figcaption></figure>
      </div>
    </section>
    <form className="bilWidth bilWeek" aria-labelledby="bil-week-title" onSubmit={event => { event.preventDefault(); onApply(week); }}>
      <header><h2 id="bil-week-title">Ställ in din rutt</h2><p>Ändra eller prova exemplet.</p></header>
      <div className="bilWeekRoute">
        {[['commute','Pendling','Mån–fre'],['charge','Laddning','Under veckan'],['trip','Helgresa','Tur och retur']].map(([key,title,context]) =>
          <details key={key} name="bil-week-stops"><summary>
            <span className="bilStopLabel">{title}<small>{context}</small></span>
            <span className="bilStopValue">{display(key)}{key === 'trip' && ' · ' + display('cadence')}</span>
            <span className="bilStopMark" aria-hidden="true" />
          </summary><div className="bilStopControls">
            <RouteField name={key} label={key === 'trip' ? 'Sträcka' : title} {...{week,setWeek}} />
            {key === 'trip' && <RouteField name="cadence" label="Hur ofta åker du?" {...{week,setWeek}} />}
          </div></details>)}
      </div>
      <div className="bilWeekEnd"><p>Jämför kostnaden för kontantköp, billån och privatleasing med din körprofil.</p><button className="uiPrimary" type="submit">Visa bilurval <span aria-hidden="true">→</span></button></div>
    </form>
  </>;
}
