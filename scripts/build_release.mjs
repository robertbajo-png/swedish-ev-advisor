import { readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { loadEnv } from 'vite';
import { auditReleaseConfig } from './verify_release_config.mjs';

// Keep Python metadata and Vite's public settings on the same environment.
async function main() {
  const env = { ...loadEnv('production', process.cwd(), ''), ...process.env,
    NEWS_BUILD_SYNC: '0', VEHICLE_DATA_MODE: 'snapshot', VITE_VEHICLE_DATA_MODE: 'snapshot' };
  const catalog = JSON.parse(await readFile('public/data/public_ev_variants.json', 'utf8'));
  const report = auditReleaseConfig(env, catalog);
  console.log(JSON.stringify(report));
  if (!report.configuration_ready) { process.exitCode = 1; return; }
  for (const args of [
    ['scripts/run_python.mjs', 'scripts/export_news_build.py'],
    ['scripts/run_python.mjs', 'scripts/generate_sitemap.py'],
    ['node_modules/vite/bin/vite.js', 'build', '--configLoader', 'runner'],
    ['scripts/run_python.mjs', 'scripts/prerender_static_routes.py'],
    ['scripts/run_python.mjs', 'scripts/verify_programmatic_seo.py'],
  ]) {
    const result = spawnSync(process.execPath, args, { env, stdio: 'inherit', windowsHide: true });
    if (result.status !== 0) { process.exitCode = 1; return; }
  }
}

main().catch(() => { console.error('Release build failed; no credentials logged.'); process.exitCode = 1; });
