import React from 'react';

// Only the exact reviewed catalog photo/qualification is eligible. If the
// notice or asset changes, retain the ordinary visible model-specific notice.
const chrCatalogNotice = 'Modellbild: Toyota C-HR+ i brittiskt Design-utförande. Färg, hjul och utrustning kan skilja från den svenska versionen.';
export const catalogImageNoticeDisclosure = car => car.brand === 'Toyota'
  && car.canonicalModel?.toLowerCase() === 'c-hr+'
  && car.image === '/media/vehicles/toyota-c-hr-press-39c5e82ee449.jpg'
  && car.imageNotice === chrCatalogNotice;

export function VehicleImageNotice({ car, disclosureId }) {
  if (!car.image || !car.imageNotice) return null;
  if (disclosureId) return <>
    <details className="vehicleImageNoticeDisclosure">
      <summary>Om modellbilden</summary>
      <p className="vehicleImageNotice">{car.imageNotice}</p>
    </details>
    {/* A closed details suppresses its descendants in Chromium's accessible
        description. Reference separate hidden text so the photo link still
        announces the full qualification, without duplicate visible text. */}
    <span hidden id={disclosureId}>{car.imageNotice}</span>
  </>;
  return <p className="vehicleImageNotice">{car.imageNotice}</p>;
}
