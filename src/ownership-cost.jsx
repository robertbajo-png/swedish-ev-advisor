
import React, { useState } from 'react';
import { calculateOwnership } from './ownership-cost.js';
import { priceTypeLabel, priceOfferEnd } from './price-evidence.js';

const currency = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 0 });
const money = (value) => currency.format(value) + ' kr';
const percent = (n) => n + ' %';
const loanFields = [
  ['down', 'Kontantinsats, kr'], ['term', 'Löptid, månader'], ['rate', 'Nominell årsränta, % (oförändrad)'],
  ['opening', 'Uppläggningsavgift, kr'], ['fee', 'Aviavgift, kr/mån'], ['balloon', 'Slutbetalning, kr'],
];
const leaseFields = [
  ['term', 'Avtalstid, månader'], ['start', 'Första avgift, kr'], ['monthly', 'Månadsavgift, kr'],
  ['includedKm', 'Ingående km under hela avtalet'], ['overMil', 'Övermil, kr/mil'],
];
const reasons = {
  'from-price': 'Endast tillverkarens frånpris. Exakt pris saknas för kontant- och lånekalkylen.',
  unverified: 'Verifierat pris för exakt variant saknas i underlaget.',
  'offer-date': 'Erbjudandet har löpt ut eller saknar bekräftad giltighet.',
};

function NumberField({ name, label, value, onChange, max, min = 0, step = 'any' }) {
  return <label className="bilCostField"><span>{label}</span><input name={name} type="number" inputMode="decimal" min={min} max={max} step={step} value={value ?? ''} onChange={(event) => onChange(name, event.target.value)} /></label>;
}

function Terms({ type, enabled, setEnabled, values, update }) {
  const isLoan = type === 'loan';
  return <details className="bilCostTerms">
    <summary>{isLoan ? 'Lånevillkor' : 'Leasingvillkor'}</summary>
    <label className="bilCostCheck"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Räkna på egna villkor</label>
    {enabled && <>
      <p>Dina egna villkor används för att räkna på ett scenario. Jämför med den effektiva räntan och villkoren i ditt avtal.</p>
      <div className="bilCostFields">{(isLoan ? loanFields : leaseFields).map(([key,label]) =>
        <NumberField key={key} name={key} label={label} value={values[key]} onChange={update} />)}</div>
      {isLoan
        ? <p>Slutbetalningen ingår en gång vid lånets slut. Vid tidigare försäljning löses återstående skuld en gång.</p>
        : <div className="bilCostChecks">{[['service','Service'],['insurance','Försäkring'],['tyres','Däck']].map(([key,label]) => <label key={key} className="bilCostCheck"><input type="checkbox" checked={Boolean(values[key])} onChange={(event) => update(key,event.target.checked)} /> {label} ingår</label>)}</div>}
      {!isLoan && <div className="bilCostFields">
        <NumberField name="monthlyIncrease" label="Känslighet: högre avgift, kr/mån" value={values.monthlyIncrease} onChange={update} max={100000} />
        <NumberField name="wear" label="Känslighet: extra slitage vid återlämning, kr" value={values.wear} onChange={update} max={100000} />
      </div>}
    </>}
  </details>;
}


function CostCell({ label, children, total }) {
  return <td data-total={total}><span className="bilMobileCostLabel" aria-hidden="true">{label}</span>{children}</td>;
}

function CostRow({ title, row, message }) {
  return <tr><th scope="row">{title}</th>{row
    ? <><CostCell label="Netto totalt" total={row.total}>{money(row.total)}</CostCell>
      <CostCell label="Kr/mån i snitt">{money(row.perMonth)}</CostCell>
      <CostCell label="Kr/mil">{money(row.perMil)}</CostCell>
      <CostCell label="Ut vid start">{money(row.cash.start)}</CostCell></>
    : <td colSpan={4}>{message}</td>}</tr>;
}

function VariantCosts({ car, assumptions, today }) {
  const [loanEnabled, setLoanEnabled] = useState(false), [leaseEnabled, setLeaseEnabled] = useState(false);
  const [loan, setLoan] = useState({}), [lease, setLease] = useState({});
  const result = calculateOwnership(car, assumptions, today, loanEnabled ? loan : null, leaseEnabled ? lease : null);
  const until = priceOfferEnd(car.priceType, car.priceValidUntil);
  const loanFlow = result.loan?.cash;
  const leaseFlow = result.lease?.cash;
  const manualConsumption = assumptions.overrideConsumption !== '' && assumptions.overrideConsumption != null;
  return <article className="bilCostVariant" data-ownership-variant={car.id}>
    <h2>{car.brand} {car.model}</h2><p>{car.variantName}</p>
    <p className="bilCostMeta">{priceTypeLabel(car.priceType) || 'Prisuppgift saknas'}{car.priceVerifiedAt && <> · Kontrollerat <time dateTime={car.priceVerifiedAt}>{car.priceVerifiedAt}</time></>}{car.price ? <> · {money(car.price)}</> : null}
      {until && <> · Giltigt t.o.m. <time dateTime={until}>{until}</time></>}</p>
    {result.reason ? <p role="status">Fyll i giltiga antaganden för att visa beräkningen.</p> : <>
      <p className="bilCostMeta">{currency.format(result.km)} km på {result.duration} månader. {result.consumption} kWh/100 km
        {manualConsumption ? result.basis === 'vehicle' ? ' · eget antagande på bilsidan' : ' · eget antagande vid elmätaren' : car.consumptionVerified ? ' · katalogens WLTP-uppgift' : ' · antagen förbrukning vid elmätaren'}.
        {' '}Drift {money(result.operatingTotal)}, varav el <span data-electricity={result.operating.electricity}>{money(result.operating.electricity)}</span>.</p>
      {car.consumptionInterval && !manualConsumption && <p className="bilCostMeta">Källans WLTP-intervall är {car.consumptionInterval}. Kalkylen använder katalogvärdet.</p>}
      <div className="bilCostTable" role="region" aria-label={'Kostnader för ' + car.model} tabIndex={0}><table>
        <thead><tr><th scope="col">Betalsätt</th><th scope="col">Netto totalt</th><th scope="col">Kr/mån i snitt</th><th scope="col">Kr/mil</th><th scope="col">Ut vid start</th></tr></thead>
        <tbody>
          <CostRow title="Kontantköp" row={result.cash} message={reasons[result.pricing?.reason]} />
          <CostRow title="Billån" row={result.loan} message={loanEnabled ? result.pricing?.reason ? reasons[result.pricing.reason] : 'Fyll i fullständiga lånevillkor.' : 'Låneoffert saknas.'} />
          <CostRow title="Privatleasing" row={result.lease} message={result.leaseReason === 'period' ? 'Avtalstiden måste vara samma som jämförelseperioden.' : leaseEnabled ? 'Fyll i fullständiga leasingvillkor.' : 'Leasingoffert saknas.'} />
        </tbody>
      </table></div>
      {result.cash && <p className="bilCostMeta">Beräknat försäljningsvärde {money(result.cash.cash.sale)} ({percent(assumptions.resalePercent)}). Värdet är ett antagande.</p>}
    </>}
    {loanFlow && <section className="bilCostFlow" aria-label="Billånets kassaflöde"><h3>Billånets betalningar</h3>
      <dl><dt>Till långivaren per månad ({loanFlow.regularMonths} månader)</dt><dd>{money(loanFlow.regular)}</dd>
        <dt>Ut vid start</dt><dd>{money(loanFlow.start)}</dd>
        {loanFlow.maturityPayment > 0 && <><dt>Slutbetalning månad {loanFlow.maturityMonth}</dt><dd>{money(loanFlow.maturityPayment)}</dd></>}
        <dt>Lösen vid försäljning</dt><dd>{money(loanFlow.settlement)}</dd>
        <dt>Försäljning efter lösen</dt><dd>{money(loanFlow.saleNet)}</dd>
        <dt>Ränta och låneavgifter i nettokostnaden</dt><dd>{money(loanFlow.interest + loanFlow.fees)}</dd>
      </dl></section>}
    {leaseFlow && <p className="bilCostMeta">Eget leasingscenario. {money(leaseFlow.monthly)}/mån i avgift och {money(leaseFlow.excess)} för övermil. Drift som ingår i avtalet har dragits av en gång. Bilen återlämnas. Ingen försäljningsintäkt ingår.</p>}
    {result.leaseSensitivity > 0 && <p className="bilCostMeta">Med högre avgift och slitage: {money(result.lease.total + result.leaseSensitivity)} totalt (ytterligare {money(result.leaseSensitivity)}).</p>}
    <Terms type="loan" enabled={loanEnabled} setEnabled={setLoanEnabled} values={loan} update={(key,value) => setLoan({...loan,[key]:value})} />
    <Terms type="lease" enabled={leaseEnabled} setEnabled={setLeaseEnabled} values={lease} update={(key,value) => setLease({...lease,[key]:value})} />
  </article>;
}

export function OwnershipCosts({ cars, assumptions, setAssumptions, link, heading = 'Ägandekostnad', fullPage = false, today }) {
  const Title = fullPage ? 'h1' : 'h2';
  const update = (field,value) => setAssumptions({ ...assumptions, [field]: value, ...(field === 'annualKm' ? {onceKm:0} : {}) });
  return <section className="bilCost vehicleContainer" id="agandekostnad" aria-labelledby="bil-cost-heading">
    <Title id="bil-cost-heading">{heading}</Title>
    <p>Se vad bilen kan kosta totalt och vad du betalar vid start. Du kan ändra körsträcka, elpris och andra antaganden.</p>
    {!cars.length ? <p>Välj en exakt bilversion för att räkna. {link('/bilar','Till katalogen')}</p> : <>
      <details className="bilCostAssumptions">
        <summary>Körsträcka, el och övriga antaganden</summary>
        <div className="bilCostFields">
          {[['months','Jämförelseperiod, månader',120,1,1],['annualKm','Körsträcka, km/år',60000,0],
            ['homePercent','Andel laddning hemma, %',100],['homeSek','Hemmaladdning, kr/kWh',50],['publicSek','Publik laddning, kr/kWh',50],
            ['overrideConsumption','Egen förbrukning, kWh/100 km',100,1],['resalePercent','Försäljningsvärde, % av inköp',100],
            ['insurance','Försäkring, kr/mån',100000],['service','Service, kr/år',100000],['tyres','Däck, kr/år',100000],['tax','Skatt, kr/år',100000]
          ].map(([name,label,max,min,step]) => <NumberField key={name} name={name} label={label} value={assumptions[name]} onChange={update} max={max} min={min} step={step} />)}
          <label className="bilCostField"><span>Den egna förbrukningens mätpunkt</span><select value={assumptions.basis} onChange={event => update('basis',event.target.value)}><option value="metered">Elmätare, laddförluster ingår</option><option value="vehicle">Bilens sida, lägg till laddförluster</option></select></label>
          {assumptions.basis === 'vehicle' && <NumberField name="lossPercent" label="Laddförlust, %" value={assumptions.lossPercent} onChange={update} max={50} />}
        </div>
        <details className="bilCostTerms"><summary>Parkering, trängselskatt och laddbox</summary>
          <div className="bilCostFields">{[['charger','Laddbox, engångskostnad i kr'],['parking','Parkering, kr/mån'],['tolls','Trängselskatt, kr/mån']].map(([name,label]) => <NumberField key={name} name={name} label={label} value={assumptions[name]} onChange={update} max={100000} />)}</div>
        </details>
        <p>Om du lämnar egen förbrukning tom används bilens WLTP-värde där det finns, annars 20 kWh/100 km som antagande.</p>
      </details>
      {cars.map(car => <VariantCosts key={car.id} {...{ car, assumptions, today }} />)}
      <p className="bilSourceContext">{link('/kallor?post=kalkyl','Källor för kalkylen')}</p>
    </>}
  </section>;
}
