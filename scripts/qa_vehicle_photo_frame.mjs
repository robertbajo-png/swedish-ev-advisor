import assert from 'node:assert/strict';

export async function assertVehiclePhotoFrame(page, label) {
  const frame = await page.evaluate(() => {
    const bounds = selector => document.querySelector(selector).getBoundingClientRect();
    const media = bounds('.vehicleHeroMedia');
    const lead = bounds('.bilVehicleLead');
    const copy = bounds('.vehicleHeroCopy');
    const photo = document.querySelector('.vehicleHeroMedia img');
    const overlay = document.querySelector('.vehicleHeroOverlay');
    return {
      overflow: document.documentElement.scrollWidth > innerWidth,
      height: media.height,
      copyAbove: media.top - copy.bottom,
      copyAlongside: media.left - copy.right,
      headerGap: media.top - bounds('.siteHeader').bottom,
      statsGap: bounds('.vehicleHeroStats').top - media.bottom,
      centerOffset: Math.abs(media.left + media.width / 2 - lead.left - lead.width / 2),
      overlayVisible: Boolean(overlay && getComputedStyle(overlay).display !== 'none'),
      imageFit: photo && getComputedStyle(photo).objectFit,
      imagePosition: photo && getComputedStyle(photo).objectPosition,
    };
  });

  assert(!frame.overflow, label + ': no horizontal overflow');
  assert(!frame.overlayVisible, label + ': no darkening over the photo');
  if (frame.imageFit) {
    assert.equal(frame.imageFit, 'contain', label + ': display the full original frame');
    assert.equal(frame.imagePosition, '50% 50%', label + ': center the image inside the frame');
  }
  if (page.viewportSize().width <= 800) {
    assert(frame.height >= 160, label + ': visible image area');
    assert(frame.headerGap >= 0 && frame.copyAbove >= 12 && frame.statsGap >= 12, label + ': header, copy and specifications stay clear');
    assert(frame.centerOffset < 1, label + ': frame centered on the mobile model grid');
  } else {
    assert(frame.copyAlongside >= 12 && frame.statsGap >= 12, label + ': copy and specifications stay clear of the desktop photo');
  }
  return frame;
}
