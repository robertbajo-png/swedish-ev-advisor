import assert from 'node:assert/strict';
import test from 'node:test';
import {displayModelName,displayVariantName,vehicleSlug} from '../src/vehicle-names.js';

test('retired inventory labels stay out of display names without changing deep links',()=>{
  const bmw='eDrive40 M Sport Business Edition (lagerbil FW37556)';
  assert.equal(displayVariantName(bmw),'eDrive40 M Sport Business Edition');
  assert.equal(displayModelName('BMW','i4',bmw),'i4 eDrive40 M Sport Business Edition');
  assert.equal(vehicleSlug('BMW','i4',bmw),'bmw-i4-edrive40-m-sport-business-edition-lagerbil-fw37556');
  const cla='CLA 200 Advanced Edition MY2027 (best\u00e4llningsbil)';
  assert.equal(displayModelName('Mercedes-Benz','Cla',cla),'CLA 200 Advanced Edition MY2027');
  assert.equal(vehicleSlug('Mercedes-Benz','Cla',cla),'mercedes-benz-cla-200-advanced-edition-my2027-lagerbil');
  assert.equal(displayVariantName('GLB 250+ Advanced Edition'),'GLB 250+ Advanced Edition');
});
