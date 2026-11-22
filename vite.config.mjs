import { defineConfig, normalizePath, resolveConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const basePath = process.env.VITE_APP_BASE_PATH || '/';
const responsiveImages = normalizePath(fileURLToPath(new URL('./src/image-variants.json', import.meta.url)));

export default defineConfig(async () => {
  // Extend the installed Vite defaults; do not replace its built-in secret rules.
  const defaults = await resolveConfig({ configFile: false, envFile: false }, 'serve');
  const privateData = normalizePath(fileURLToPath(new URL('./data', import.meta.url)));
  return {
    base: basePath.endsWith('/') ? basePath : `${basePath}/`,
    plugins: [react(), {
      name: 'public-responsive-image-manifest',
      apply: 'build',
      async load(id) {
        if (normalizePath(id) !== responsiveImages) return null;
        const registry = JSON.parse(await readFile(responsiveImages, 'utf8'));
        // Derivative digests are checked before release, not by the browser.
        return JSON.stringify(Object.fromEntries(Object.entries(registry).map(([url, image]) => [
          url, { ...image, variants: image.variants.map(({ url, width }) => ({ url, width })) },
        ])));
      },
    }, {
      name: 'canonical-static-preview',
      configurePreviewServer(server) {
        server.middlewares.use((request, response, next) => {
          const url = new URL(request.url, 'http://localhost');
          // Match Pages' directory indexes, not Vite's generic SPA root fallback.
          if (/^\/[a-z0-9-]+(?:\/[a-z0-9-]+)*\/?$/.test(url.pathname)) {
            const index = path.join(server.config.build.outDir, url.pathname, 'index.html');
            if (existsSync(index)) request.url = url.pathname.replace(/\/$/, '') + '/index.html' + url.search;
          }
          next();
        });
      },
    }],
    server: {
      fs: { deny: [...defaults.server.fs.deny, `${privateData}/**`, '**/.dev.vars*', '**/.wrangler/**'] },
      watch: { ignored: [`${privateData}/**`, '**/.wrangler/**'] },
    },
  };
});
