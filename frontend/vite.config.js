import { defineConfig } from 'vite';

export default defineConfig({
  esbuild: { jsx: 'automatic' },
  server: { proxy: { '/api': process.env.VITE_DEV_API_TARGET || 'http://localhost:8000' } },
});
