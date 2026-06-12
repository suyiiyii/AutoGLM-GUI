/**
 * Start backend services (mock LLM + mock agent + AutoGLM-GUI) before E2E tests.
 *
 * Uses child_process to manage the Python launcher script.  The PID is written
 * to a file so globalTeardown can kill it.
 */
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { sleep, terminateProcessTree } from './processTree';

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
  const projectRoot = path.resolve(__dirname, '..', '..');
  const urlsPath = path.resolve(__dirname, '.service_urls.json');
  const pidPath = path.resolve(__dirname, '.services_pid');

  console.log('[globalSetup] Starting E2E services...');

  // Stop services from the previous E2E run, if that run did not clean up.
  try {
    const previousPid = Number(fs.readFileSync(pidPath, 'utf-8').trim());
    if (Number.isFinite(previousPid)) {
      await terminateProcessTree(previousPid);
    }
  } catch {
    /* PID file may not exist */
  }

  // Cleanup old files
  try {
    fs.unlinkSync(urlsPath);
  } catch {
    /* file may not exist */
  }
  try {
    fs.unlinkSync(pidPath);
  } catch {
    /* file may not exist */
  }

  // Wait for ports to be fully released by the OS
  await sleep(3000);

  console.log('[globalSetup] Project root:', projectRoot);

  // Start services with retry on port-in-use
  let proc: ReturnType<typeof spawn> | null = null;
  const coverageEnabled = process.env.COVERAGE_E2E_FRONTEND === '1';
  for (let attempt = 0; attempt < 3; attempt++) {
    const args = [
      'run',
      'python',
      'scripts/start_e2e_services.py',
      '--output',
      urlsPath,
    ];
    if (coverageEnabled) {
      args.push('--coverage');
    }
    proc = spawn('uv', args, {
      cwd: projectRoot,
      stdio: 'inherit',
      detached: true,
    });

    // Wait for both backend health and the launcher-written URL file.
    const deadline = Date.now() + 30000;
    let started = false;
    while (Date.now() < deadline) {
      try {
        const resp = await fetch('http://127.0.0.1:8000/api/health');
        if (resp.status === 200) {
          const urls = readServiceUrls(urlsPath);
          if (urls) {
            console.log('[globalSetup] Services ready, URLs:', urls);
            started = true;
            break;
          }
        }
      } catch {
        // Not ready — but check if the process exited with error
        if (proc && proc.exitCode !== null) {
          // Process died — port likely in use, retry
          console.log(
            `[globalSetup] Attempt ${attempt + 1}: process exited, retrying...`
          );
          break;
        }
      }
      await sleep(500);
    }
    if (started && proc?.pid) {
      fs.writeFileSync(pidPath, String(proc.pid));
      return;
    }
    // Kill the failed process and wait before retry
    if (proc?.pid) {
      await terminateProcessTree(proc.pid);
      await sleep(1000);
    }
  }

  throw new Error('E2E services failed to start after 3 attempts');
}

export default globalSetup;
