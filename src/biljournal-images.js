
import rights from './image-rights.json' with { type: 'json' };

export const coverPhoto = '/media/vehicles/hyundai-inster-74c89ece773a.jpg';
const ccLicense = 'https://creativecommons.org/licenses/by-sa/4.0/';

export const biljournalPhotos = {
  'kia|ev3': {
    asset_url: '/media/biljournal/kia-ev3-dsc-7147.jpg',
    title: 'Kia EV3 DSC 7147.jpg', author: 'Alexander Migl', credit: 'Alexander Migl / Wikimedia Commons',
    source_url: 'https://commons.wikimedia.org/wiki/File:Kia_EV3_DSC_7147.jpg',
    license_id: 'CC BY-SA 4.0', license_url: ccLicense,
    notice: 'Kia EV3, Stuttgart 2024. Utrustningen kan skilja mellan versioner.',
    changes: 'Nedskalad JPEG från Wikimedia Commons. Miniatyrer kan beskäras.',
  },
  'renault|5': {
    asset_url: '/media/biljournal/renault-5-gims-2024.jpg',
    title: 'Renault 5 E-Tech Electric GIMS 2024 1X7A2164.jpg', author: 'Alexander-93', credit: 'Alexander-93 / Wikimedia Commons',
    source_url: 'https://commons.wikimedia.org/wiki/File:Renault_5_E-Tech_Electric_GIMS_2024_1X7A2164.jpg',
    license_id: 'CC BY-SA 4.0', license_url: ccLicense,
    notice: 'Arkivbild · Renault 5 E-Tech Electric, Genève 2024. Utrustningen kan skilja mellan versioner.',
    changes: 'Nedskalad JPEG från Wikimedia Commons. Miniatyrer kan beskäras.',
  },
};

export function vehiclePhotoOverride(brand, model) {
  const key = [brand, model].map((name) => String(name || '').trim().toLowerCase()).join('|');
  return Object.hasOwn(biljournalPhotos, key) ? biljournalPhotos[key] : null;
}

export function photoCredit(url) {
  const photo = Object.values(biljournalPhotos).find((item) => item.asset_url === url)
    || rights.assets.find((item) => item.asset_url === url);
  return photo && url === coverPhoto ? { ...photo, credit: '© ' + photo.credit } : photo;
}

export function reviewedNewsPhoto(image) {
  if (!image || ![image.source_url, image.license_url].some((url) => url?.endsWith('-3172684'))) return image;
  const asset = biljournalPhotos['renault|5'];
  return {
    ...image, url: asset.asset_url, width: 1280, height: 854, alt: 'Gul Renault 5 E-Tech Electric på bilsalongen i Genève',
    caption: asset.notice, credit: asset.credit, source_url: asset.source_url, license_url: asset.license_url,
    license_name: asset.license_id, edits: asset.changes,
  };
}
