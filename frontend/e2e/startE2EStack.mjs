/**
 * Playwright webServer launcher that boots the full E2E stack.
 *
 * Playwright starts this command before running tests.  We therefore start the
 * backend services (mock LLM + mock agent + AutoGLM-GUI backend) ourselves,
 * wait for the dynamic backend URL to be written to `.service_urls.json`, and
 * then start the Vite dev server with `VITE_PROXY_TARGET` set to that URL.
 *
 * Keeping the whole stack inside one webServer process avoids relying on the
 * ordering between `globalSetup` and the webServer, which are started in
 * parallel by Playwright.
 */
import { execFile, spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { promisify } from 'util';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..', '..');
const frontendRoot = path.resolve(__dirname, '..');
const urlsPath = path.resolve(__dirname, '.service_urls.json');
const pidPath = path.resolve(__dirname, '.services_pid');

const execFileAsync = promisify(execFile);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function terminateProcessTree(pid) {
  if (!Number.isFinite(pid)) {
    return;
  }

  if (process.platform === 'win32') {
    try {
      await execFileAsync('taskkill', ['/PID', String(pid), '/T', '/F']);
    } catch {
      // process tree is already gone
    }
    return;
  }

  // SIGINT lets uvicorn subprocesses run atexit handlers, which is needed for
  // Python coverage data to be flushed.  Fall back to SIGTERM/SIGKILL.
  try {
    process.kill(-pid, 'SIGINT');
  } catch {
    return;
  }
  await sleep(3000);
  try {
    process.kill(-pid, 'SIGTERM');
  } catch {
    return;
  }
  await sleep(1000);
  try {
    process.kill(-pid, 'SIGKILL');
  } catch {
    // process group is already gone
  }
}

async function cleanupPreviousRun() {
  try {
    const pid = Number(fs.readFileSync(pidPath, 'utf-8').trim());
    console.log(
      `[startE2EStack] Stopping previous backend process group ${pid}`
    );
    await terminateProcessTree(pid);
  } catch {
    // PID file may not exist
  }

  for (const filePath of [urlsPath, pidPath]) {
    try {
      fs.unlinkSync(filePath);
    } catch {
      // file may not exist
    }
  }

  // Give the OS a moment to fully release the ports.
  await sleep(500);
}

async function waitForBackendUrl(timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const urls = JSON.parse(fs.readFileSync(urlsPath, 'utf-8'));
      if (urls.backend_url) {
        return urls.backend_url;
      }
      throw new Error(
        `${urlsPath} exists but does not contain backend_url; cannot determine backend proxy target`
      );
    } catch (err) {
      if (err instanceof Error && err.message.includes('does not contain')) {
        throw err;
      }
      // File may not exist yet or is partially written — keep waiting.
    }
    await sleep(250);
  }
  throw new Error(
    `Timed out waiting for ${urlsPath} to contain the dynamic backend URL`
  );
}

async function main() {
  await cleanupPreviousRun();

  console.log('[startE2EStack] Starting backend services...');
  // Start backend services.  Keep the child in the same process group as this
  // launcher so Playwright's teardown of the webServer process kills the whole
  // stack.  Coverage flushing for the backend is handled by the Python
  // launcher on SIGINT/SIGTERM.
  const serviceProc = spawn(
    'uv',
    [
      'run',
      'python',
      'scripts/start_e2e_services.py',
      '--dynamic-ports',
      '--output',
      urlsPath,
    ],
    {
      cwd: projectRoot,
      stdio: 'inherit',
    }
  );

  const backendUrl = await waitForBackendUrl();
  console.log(`[startE2EStack] backend_url=${backendUrl}`);

  const viteProc = spawn('pnpm', ['dev'], {
    cwd: frontendRoot,
    stdio: 'inherit',
    env: {
      ...process.env,
      VITE_PROXY_TARGET: backendUrl,
    },
  });

  // Exit when either child exits.  Because the children share our process
  // group, Playwright can stop the whole stack by killing this process.
  serviceProc.on('exit', (code, signal) => {
    console.log('[startE2EStack] Backend services exited unexpectedly');
    viteProc.kill('SIGTERM');
    process.exit(code ?? (signal ? 1 : 0));
  });
  viteProc.on('exit', (code, signal) => {
    serviceProc.kill('SIGTERM');
    process.exit(code ?? (signal ? 1 : 0));
  });
}

main().catch(error => {
  console.error('[startE2EStack]', error);
  process.exit(1);
});
