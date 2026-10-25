import React from 'react';
import { ArrowUpRight, Mail } from 'lucide-react';
import { PUBLIC_OPERATOR, SITE_NAME } from './site-info.js';
import privacyContent from './privacy-content.json';
import imageRights from './image-rights.json';
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
      <p>Uppdaterad {privacyContent.updated}</p>
      {privacyContent.sections.map(section => <section key={section.id}><h2>{section.title}</h2>{section.paragraphs.map(paragraph => <p key={paragraph}>{paragraph}</p>)}</section>)}
      <section className="infoReferences"><h2>Mer information</h2>{privacyContent.references.map(reference => <a key={reference.url} href={reference.url} target="_blank" rel="noreferrer">{reference.label}<ArrowUpRight size={15} /></a>)}</section>
    </> : <><section><h2>Hjälp oss rätta en uppgift</h2><p>Ange gärna vilken bilvariant eller artikel det gäller och länka till tillverkarens aktuella uppgifter. Vi kontrollerar rättelser mot källan innan biluppgifter ändras.</p></section><section id="bildkallor"><h2>Bildkällor</h2>{imageRights.assets.map(asset => <div key={asset.asset_url}><p><a href={asset.source_url} target="_blank" rel="noreferrer">{asset.credit}</a> · <a href={asset.license_url} target="_blank" rel="noreferrer">{asset.license_id}</a></p><p>{asset.changes}</p></div>)}</section></>}
  </article>;
}
