import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: 'http://localhost:3000',
  },
  webServer: {
    // Start the full E2E stack (backend services + Vite) and proxy the frontend
    // to the dynamic backend port via VITE_PROXY_TARGET.
    command: 'node e2e/startE2EStack.mjs',
    url: 'http://localhost:3000',
    timeout: 120000,
    reuseExistingServer: !process.env.CI,
  },
});
