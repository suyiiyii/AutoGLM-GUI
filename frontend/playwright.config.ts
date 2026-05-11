import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  retries: 0,
  workers: 1,
  globalSetup: './e2e/globalSetup.ts',
  globalTeardown: './e2e/globalTeardown.ts',
  use: {
    baseURL: 'http://localhost:3000',
  },
  webServer: {
    // Only Vite dev server — backend services are managed by globalSetup
    command: 'pnpm dev',
    url: 'http://localhost:3000',
    timeout: 30000,
    reuseExistingServer: true,
  },
});
