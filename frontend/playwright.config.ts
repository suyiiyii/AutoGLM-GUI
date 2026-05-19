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
    command: 'node e2e/startPlaywrightWebServer.mjs',
    url: 'http://127.0.0.1:3000',
    timeout: 30000,
    reuseExistingServer: false,
  },
});
