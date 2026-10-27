import { defineConfig, normalizePath, resolveConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';

const basePath = process.env.VITE_APP_BASE_PATH || '/';

export default defineConfig(async () => {
  // Extend the installed Vite defaults; do not replace its built-in secret rules.
  const defaults = await resolveConfig({ configFile: false, envFile: false }, 'serve');
  const privateData = normalizePath(fileURLToPath(new URL('./data', import.meta.url)));
  return {
    base: basePath.endsWith('/') ? basePath : `${basePath}/`,
    plugins: [react()],
    server: {
      fs: { deny: [...defaults.server.fs.deny, `${privateData}/**`, '**/.dev.vars*', '**/.wrangler/**'] },
      watch: { ignored: [`${privateData}/**`, '**/.wrangler/**'] },
    },
  };
});
