import { chromium } from 'playwright';

export async function launchQaBrowser({ env = process.env, platform = process.platform,
  launch = options => chromium.launch(options) } = {}) {
  const channel = env.PLAYWRIGHT_CHANNEL;
  if (channel) {
    if (!['chrome', 'msedge'].includes(channel)) throw new Error('Unsupported QA browser channel');
    return launch({ headless: true, channel });
  }
  try { return await launch({ headless: true }); }
  catch (error) {
    if (platform !== 'win32') throw error;
    return launch({ headless: true, channel: 'msedge' });
  }
}
