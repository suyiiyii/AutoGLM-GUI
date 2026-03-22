import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { tanstackRouter } from '@tanstack/router-plugin/vite';
import path from 'path';

// https://vitejs.dev/config/
const apiProxyTarget =
  process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000';

export default defineConfig({
  define: {
    __BACKEND_VERSION__: JSON.stringify(
      process.env.VITE_BACKEND_VERSION || 'unknown'
    ),
    __DEVTOOLS_ENABLED__: JSON.stringify(process.env.NODE_ENV !== 'production'),
  },
  plugins: [
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    react(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      '/socket.io': {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
