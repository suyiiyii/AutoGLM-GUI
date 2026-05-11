import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { tanstackRouter } from '@tanstack/router-plugin/vite';
import { execSync } from 'node:child_process';
import path from 'path';

// Short commit of the working tree at build time, so a deployed build can be
// traced back to a commit (the package version is the same across branches).
// Appends "-dirty" when there are uncommitted changes to tracked files.
function resolveBuildCommit() {
  if (process.env.VITE_GIT_HASH) return process.env.VITE_GIT_HASH;
  const git = cmd =>
    execSync(cmd, { stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim();
  try {
    const hash = git('git rev-parse --short HEAD');
    const dirty = git('git status --porcelain -uno').length > 0;
    return dirty ? `${hash}-dirty` : hash;
  } catch {
    return 'unknown';
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  define: {
    __BACKEND_VERSION__: JSON.stringify(
      process.env.VITE_BACKEND_VERSION || 'unknown'
    ),
    __GIT_HASH__: JSON.stringify(resolveBuildCommit()),
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
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      '/socket.io': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
