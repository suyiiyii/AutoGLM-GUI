import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { terminateProcessTree } from './processTree';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function globalTeardown() {
  const pidPath = path.resolve(__dirname, '.service_pids.json');
  const urlsPath = path.resolve(__dirname, '.service_urls.json');

  // Kill the detached processes we started for the E2E stack.
  try {
    const payload = JSON.parse(fs.readFileSync(pidPath, 'utf-8')) as {
      servicePid?: number;
      vitePid?: number;
    };
    for (const pid of [payload.vitePid, payload.servicePid]) {
      if (Number.isFinite(pid)) {
        console.log(`[globalTeardown] Killing process group ${pid}`);
        await terminateProcessTree(pid as number);
      }
    }
  } catch {
    // PID file may not exist
  }

  // Cleanup ONLY the processes we started (by PID file).
  // We do NOT kill processes by port or name — that would affect
  // unrelated services the user may be running.

  // Cleanup files
  try {
    fs.unlinkSync(pidPath);
  } catch {
    /* PID file may not exist or process already dead */
  }
  try {
    fs.unlinkSync(urlsPath);
  } catch {
    /* PID file may not exist or process already dead */
  }

  console.log('[globalTeardown] Cleanup complete');
}

export default globalTeardown;
