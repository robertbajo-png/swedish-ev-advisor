import React from 'react';
import { ArrowUpRight, Mail } from 'lucide-react';
import { PUBLIC_OPERATOR, SITE_NAME } from './site-info.js';
import './info-pages.css';

export function InfoPage({ type }) {
  const privacy = type === 'privacy';
  const operator = PUBLIC_OPERATOR;
  return <article className="infoPage" aria-labelledby="info-title">
    <header><span className="vehicleEyebrow">{SITE_NAME}</span>
      <h1 id="info-title">{privacy ? 'Dina uppgifter.' : 'Kontakta oss.'}</h1>
      <p>{privacy ? 'Vad som händer med din sökning och vilka tjänster som används.' : 'Frågor, rättelser och synpunkter på Elbilsagenten.'}</p>
    </header>
    {!operator.configured ? <section className="infoNotice" role="status"><h2>Förhandsversion</h2><p>Ansvarig aktör och kontaktuppgifter fastställs före lansering.</p></section> : <section>
      <h2>{privacy ? 'Ansvarig för tjänsten' : operator.name}</h2>
      {privacy && <p>{operator.name} ansvarar för {SITE_NAME}.</p>}
      {operator.organizationNumber && <p>Organisationsnummer: {operator.organizationNumber}</p>}
      <a className="infoContact" href={operator.emailHref}><Mail size={18} />{operator.email}</a>
    </section>}
    {privacy ? <>
      <section><h2>När du söker efter en bil</h2><p>Din beskrivning, budget och andra val används för att föreslå bilar. När AI-rådgivning används skickas söktext och relevanta biluppgifter till OpenAI. Skriv inte personnummer, hälsouppgifter eller andra känsliga personuppgifter i sökrutan.</p><p>Du kan också filtrera och jämföra bilar utan att skriva en personlig beskrivning.</p></section>
      <section><h2>Drift och skydd mot missbruk</h2><p>Cloudflare levererar webbplatsen och hanterar anslutningen. För kostnads- och anropsgränser används en dagsspecifik, kryptografiskt skyddad identifierare baserad på IP-adressen. Bil- och nyhetsuppgifter lagras i Supabase. Söktext ingår inte i bilkatalogen.</p></section>
      <section><h2>Kakor och lokal lagring</h2><p>Appen lägger inte till annonseringskakor eller ett eget analysverktyg. Dina aktuella val hanteras i sidans minne. Infrastrukturens eventuella säkerhetskakor behöver bedömas separat före lansering.</p></section>
      <section><h2>Frågor om dina uppgifter</h2><p>{operator.configured ? 'Kontakta ansvarig aktör via mejlen ovan om du har frågor om behandlingen av dina uppgifter.' : 'Kontaktväg och fullständig information om personuppgiftsbehandling ska vara klara före lansering.'}</p><p>Denna sida är inte en bekräftelse på färdig integritetsgranskning. Lagringstider, rättslig grund och leverantörsinställningar ska fastställas före en öppen release.</p></section>
      <section className="infoReferences"><h2>Mer information</h2><a href="https://www.imy.se/privatperson/dataskydd/" target="_blank" rel="noreferrer">Integritetsskyddsmyndigheten <ArrowUpRight size={15} /></a><a href="https://www.pts.se/internet-och-telefoni/kakor-cookies/" target="_blank" rel="noreferrer">PTS om kakor <ArrowUpRight size={15} /></a></section>
    </> : <section><h2>Hjälp oss rätta en uppgift</h2><p>Ange gärna vilken bilvariant eller artikel det gäller och länka till tillverkarens aktuella uppgifter. Vi kontrollerar rättelser mot källan innan biluppgifter ändras.</p></section>}
  </article>;
}
