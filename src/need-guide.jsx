import React from 'react';
import { ArrowRight } from 'lucide-react';
import guides from './need-guides.json';

const names = { familj: 'Familjeelbilar', vinter: 'Fyrhjulsdrift och vinter', dragkrok: 'Elbilar med dragkrok', 'under-500000': 'Under 500 000 kr', 'lang-rackvidd': 'Lång räckvidd' };

export function NeedGuide({ slug, appPath, navigate }) {
  const guide = guides[slug];
  if (!guide) return null;
  return <section className="needGuide" aria-labelledby="need-guide-title">
    <div><span className="vehicleEyebrow">Inför ditt bilval</span><h2 id="need-guide-title">{guide.heading}</h2><p>{guide.intro}</p><p className="needGuideCriteria">{guide.criteria}</p></div>
    <div className="needGuideQuestions">{guide.questions.map(([question, answer]) => <details key={question}><summary>{question}</summary><p>{answer}</p></details>)}</div>
    <nav aria-label="Fler bilbehov">{guide.related.map((key) => <a key={key} href={appPath('/' + key)} onClick={(event) => { if (!event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) { event.preventDefault(); navigate('/' + key); } }}>{names[key]}<ArrowRight size={16} aria-hidden="true" /></a>)}</nav>
  </section>;
}
