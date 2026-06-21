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
    // Keep a full Playwright trace for every run (not just failures). A trace
    // has a real timeline — you can scrub through each action, network request,
    // and DOM snapshot with its wall-clock duration. The video alone drops
    // idle/network-wait frames, so it plays back much faster than real time;
    // the trace is what shows the actual timing and the operations in between.
    trace: 'on',
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
