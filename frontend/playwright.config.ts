import { execFileSync } from 'node:child_process';
import { defineConfig } from '@playwright/test';

function resolveFrontendPort(): number {
  const configured = process.env.PLAYWRIGHT_FRONTEND_PORT;
  if (configured) {
    return Number(configured);
  }

  const discovered = execFileSync(
    'python3',
    [
      '-c',
      "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1]);s.close()",
    ],
    { encoding: 'utf-8' }
  ).trim();
  process.env.PLAYWRIGHT_FRONTEND_PORT = discovered;
  return Number(discovered);
}

const frontendPort = resolveFrontendPort();

export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  retries: 0,
  workers: 1,
  globalSetup: './e2e/globalSetup.ts',
  globalTeardown: './e2e/globalTeardown.ts',
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
  },
  webServer: {
    command: `node e2e/startPlaywrightWebServer.mjs --frontend-port ${frontendPort}`,
    url: `http://127.0.0.1:${frontendPort}`,
    timeout: 30000,
    reuseExistingServer: false,
  },
});
