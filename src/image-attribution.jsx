import React from 'react';
import imageRights from './image-rights.json';
import imageVariants from './image-variants.json';

export function ImageAttribution({ car }) {
  const asset = imageRights.assets.find(item => item.asset_url === car?.image);
  if (!asset) return null;
  const notice = `Modellbild · utrustning kan skilja${imageVariants[car.image] ? ' · storlek och format anpassade' : ''}`;
  return <div className="vehicleImageAttribution" title={`${asset.credit}. ${notice}. ${asset.changes}`}>
    <span className="vehicleImageCreditLine"><a href={asset.source_url} target="_blank" rel="noreferrer" title={asset.credit}>Foto: {asset.author}</a>
    <span aria-hidden="true"> · </span>
    <a href={asset.license_url} target="_blank" rel="noreferrer">{['Polestar-editorial', 'Manufacturer-media-use'].includes(asset.license_id) ? 'Pressbild' : asset.license_id}</a></span>
    <span className="vehicleImageNotice srOnly">{notice}. {asset.changes}</span>
  </div>;
}
