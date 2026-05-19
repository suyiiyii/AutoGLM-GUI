/**
 * Wait for the E2E stack launched by Playwright's webServer command.
 */
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { sleep } from './processTree';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

type ServiceUrls = {
  llm_url: string;
  agent_url: string;
  backend_url: string;
  frontend_url: string;
};

function readServiceUrls(urlsPath: string): ServiceUrls | null {
  try {
    return JSON.parse(fs.readFileSync(urlsPath, 'utf-8')) as ServiceUrls;
  } catch {
    return null;
  }
}

async function globalSetup() {
  const urlsPath = path.resolve(__dirname, '.service_urls.json');

  console.log('[globalSetup] Waiting for E2E stack...');

  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const urls = readServiceUrls(urlsPath);
    if (urls) {
      try {
        const resp = await fetch(`${urls.backend_url}/api/health`);
        if (resp.status === 200) {
          console.log('[globalSetup] Services ready, URLs:', urls);
          return;
        }
      } catch {
        // Still booting.
      }
    }
    await sleep(500);
  }

  throw new Error('E2E stack failed to become ready within 30s');
}

export default globalSetup;
