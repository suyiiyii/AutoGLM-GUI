import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  retries: 0,
  workers: 1,
  // HTML report bundles each test's video, trace, and screenshots so it can be
  // uploaded from CI and opened locally for debugging.
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],
  use: {
    baseURL: 'http://localhost:3000',
    // Record a video for every test so any run can be reviewed after the fact.
    video: 'on',
    // Keep a full Playwright trace only for failures — enough to step through
    // the exact failing interaction without paying the cost on every pass.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
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
