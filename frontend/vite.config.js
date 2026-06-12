import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { tanstackRouter } from '@tanstack/router-plugin/vite';
import { execSync } from 'node:child_process';
import fs from 'fs';
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

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

/**
 * Resolve the backend proxy target for the Vite dev server.
 *
 * During E2E tests, `scripts/start_e2e_services.py --dynamic-ports` writes the
 * chosen backend URL to `frontend/e2e/.service_urls.json`.  When that file is
 * present (and no explicit override is set), use it so the frontend proxies to
 * the correct dynamic backend port.  Otherwise fall back to the historical
 * fixed port for manual `pnpm dev` usage.
 */
async function resolveBackendProxyTarget() {
  if (process.env.VITE_PROXY_TARGET) {
    return process.env.VITE_PROXY_TARGET;
  }

  const urlsPath = path.resolve(__dirname, 'e2e', '.service_urls.json');
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    try {
      const urls = JSON.parse(fs.readFileSync(urlsPath, 'utf-8'));
      if (urls.backend_url) {
        return urls.backend_url;
      }
    } catch {
      // File may not exist yet; globalSetup writes it after starting services.
    }
    await sleep(250);
  }

  return 'http://localhost:8000';
}

// https://vitejs.dev/config/
export default defineConfig(async () => {
  const backendProxyTarget = await resolveBackendProxyTarget();

  return {
    define: {
      __BACKEND_VERSION__: JSON.stringify(
        process.env.VITE_BACKEND_VERSION || 'unknown'
      ),
      __GIT_HASH__: JSON.stringify(resolveBuildCommit()),
      __DEVTOOLS_ENABLED__: JSON.stringify(
        process.env.NODE_ENV !== 'production'
      ),
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
          target: backendProxyTarget,
          changeOrigin: true,
          ws: true,
        },
        '/socket.io': {
          target: backendProxyTarget,
          changeOrigin: true,
          ws: true,
        },
      },
    },
  };
});
