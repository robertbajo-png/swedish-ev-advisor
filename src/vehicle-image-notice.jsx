import React from 'react';

// Catalog-only: keep each existing complete qualification accessible through
// its own disclosure rather than laying unstyled text across a card border.
// The caller is deliberately restricted to catalog cards; detail/compare
// surfaces still expose their model-specific qualifier in ordinary text.
export const catalogImageNoticeDisclosure = car => Boolean(car.image && car.imageNotice);

export function VehicleImageNotice({ car, disclosureId }) {
  if (!car.image || !car.imageNotice) return null;
  if (disclosureId) return <>
    <details className="vehicleImageNoticeDisclosure">
      <summary aria-label={`Om modellbilden för ${car.brand} ${car.canonicalModel || car.model}`}>Om modellbilden</summary>
      <p className="vehicleImageNotice">{car.imageNotice}</p>
    </details>
    {/* A closed details suppresses its descendants in Chromium's accessible
        description. Reference separate hidden text so the photo link still
        announces the full qualification, without duplicate visible text. */}
    <span hidden id={disclosureId}>{car.imageNotice}</span>
  </>;
  return <p className="vehicleImageNotice">{car.imageNotice}</p>;
}
