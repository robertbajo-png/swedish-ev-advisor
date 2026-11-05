import { readFile, mkdir } from 'node:fs/promises';
import { launchQaBrowser } from './qa_browser.mjs';

const font = await readFile('public/fonts/manrope-latin-variable.woff2');
const browser = await launchQaBrowser();
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.route('**/*', (route) => route.abort());
  await page.setContent(`<html lang="sv"><head><style>@font-face{font-family:Manrope;src:url(data:font/woff2;base64,${font.toString('base64')})}*{box-sizing:border-box}body{margin:0;background:#f7f7f4;color:#171b1c;font-family:Manrope,Arial,sans-serif;padding:64px 76px;border-top:12px solid #245e5b}.brand{font-size:30px;font-weight:800;color:#245e5b}h1{font-size:68px;line-height:1.1;max-width:900px;margin:64px 0 28px;font-weight:700}p{font-size:26px;color:#697374;margin:0}.domain{margin-top:54px;font-size:22px;color:#245e5b}</style></head><body><div class="brand">Elbilsagenten</div><h1>Hitta elbilen<br>som passar dig.</h1><p>Jämför elbilar på den svenska marknaden.</p><div class="domain">elbilsagenten.se</div></body></html>`);
  await page.evaluate(() => document.fonts.ready);
  await mkdir('public/media', { recursive: true });
  await page.screenshot({ path: 'public/media/elbilsguiden-share.png' });
  console.log(JSON.stringify({ output: 'public/media/elbilsguiden-share.png', width: 1200, height: 630, third_party_images: false }));
} finally { await browser.close(); }
