import registry from './home-featured-photos.json' with { type: 'json' };
import { coverPhoto } from './biljournal-images.js';
import { assetPath } from './preview-paths.js';

// A home-only photo choice. The canonical record and image stay unchanged on
// detail, catalog, comparison, advisor and all other routes.
export function featuredHomePhoto(car) {
  const key = [car.brand, car.canonicalModel].map(v => String(v || '').trim().toLowerCase()).join('|');
  return registry.assets.find(photo => photo.placement === 'home_featured' && photo.status === 'documented'
    && photo.model_key === key && photo.replaces_only_home_image === car.image
    && photo.model_image_notice === car.imageNotice && car.imageFullFrame
    && photo.full_frame && photo.publisher_display?.url && assetPath(photo.publisher_display.url)) || null;
}

export function browseCarCoverage(car) {
  return [car.price, car.rangeVerified, car.dcVerified, car.towingVerified].filter(value => value != null).length;
}

export function featuredCarsForHome(cars, isStart) {
  const browseCars = [...cars].sort((a,b) => browseCarCoverage(b) - browseCarCoverage(a));
  const pool = isStart ? browseCars.filter(car => car.image !== coverPhoto) : browseCars;
  const featured = [];
  for (const car of pool) {
    if (car.image && !featured.some(item => item.brand === car.brand) && featured.length < 3) featured.push(car);
  }
  if (featured.length < 3) for (const car of pool) {
    if (!featured.some(item => item.canonicalModel === car.canonicalModel && item.brand === car.brand) && featured.length < 3) featured.push(car);
  }
  return featured;
}

export function useFeaturedHomePhoto(car) {
  const photo = featuredHomePhoto(car);
  return photo ? { ...car, image: photo.publisher_display.url, imageFullFrame: true, imageNotice: photo.model_image_notice } : car;
}
