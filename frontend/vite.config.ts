import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

// GitHub Pages deploys to https://<owner>.github.io/<repo>/,
// so Vite needs base = '/voiceDeck/' for asset paths to resolve.
// Local dev (`npm run dev`) is unaffected — dev server proxies API/WS.
const repoBase = '/voiceDeck/';

export default defineConfig({
  base: repoBase,
  plugins: [react()],
  server: {
    proxy: {
      '/api':    'http://localhost:8080',
      '/health': 'http://localhost:8080',
      '/ws':     { target: 'ws://localhost:8080', ws: true },
    },
  },
  build: {
    // Explicit output for clarity; default already is 'dist'.
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
  },
});
