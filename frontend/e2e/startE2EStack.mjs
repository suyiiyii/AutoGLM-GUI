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
import { execFile, execFileSync, spawn } from 'child_process';
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

// References to spawned child processes, kept in scope so we can clean them up
// on errors, timeouts, or signals from Playwright.
let serviceProc;
let viteProc;
let isShuttingDown = false;

async function terminateProcessTree(pid) {
  if (!Number.isFinite(pid)) {
    return;
  }

  if (process.platform === 'win32') {
    try {
      await execFileAsync('taskkill', ['/PID', String(pid), '/T']);
    } catch {
      // process tree is already gone
    }
    await sleep(3000);
    try {
      await execFileAsync('taskkill', ['/PID', String(pid), '/T', '/F']);
    } catch {
      // process tree is already gone
    }
    return;
  }

  const pids = [pid, ...(await collectChildPids(pid))];

  // SIGINT lets uvicorn subprocesses run atexit handlers, which is needed for
  // Python coverage data to be flushed.  Fall back to SIGTERM/SIGKILL.
  signalPids(pids, 'SIGINT');
  await sleep(3000);
  signalPids(pids, 'SIGTERM');
  await sleep(1000);
  signalPids(pids, 'SIGKILL');
}

async function collectChildPids(pid) {
  let stdout;
  try {
    ({ stdout } = await execFileAsync('pgrep', ['-P', String(pid)]));
  } catch {
    return [];
  }

  const childPids = stdout
    .split('\n')
    .map(line => Number(line.trim()))
    .filter(Number.isFinite);
  const descendants = [];
  for (const childPid of childPids) {
    descendants.push(childPid, ...(await collectChildPids(childPid)));
  }
  return descendants;
}

function signalPids(pids, signal) {
  for (const pid of pids) {
    try {
      process.kill(pid, signal);
    } catch {
      // process is already gone
    }
  }
}

function readSavedPids() {
  const raw = fs.readFileSync(pidPath, 'utf-8').trim();
  const legacyPid = Number(raw);
  if (Number.isFinite(legacyPid)) {
    return [legacyPid];
  }

  const pidData = JSON.parse(raw);
  const pids = [];
  if (Number.isFinite(pidData.launcher_pid)) {
    pids.push(pidData.launcher_pid);
  }
  if (Array.isArray(pidData.service_pids)) {
    pids.push(...pidData.service_pids.filter(Number.isFinite));
  }
  return [...new Set(pids)];
}

function signalBackendProcess(signal = 'SIGINT') {
  const pids = [];
  try {
    pids.push(...readSavedPids());
  } catch {
    // PID file may not exist or may be partially written.
  }
  if (serviceProc?.pid) {
    pids.push(serviceProc.pid);
  }
  const uniquePids = [...new Set(pids)];
  if (uniquePids.length === 0) {
    return;
  }

  if (process.platform === 'win32') {
    for (const pid of uniquePids) {
      try {
        execFileSync('taskkill', ['/PID', String(pid), '/T'], {
          stdio: 'ignore',
        });
      } catch {
        // process tree is already gone
      }
    }
    return;
  }

  for (const pid of uniquePids) {
    try {
      process.kill(pid, signal);
    } catch {
      // process is already gone
    }
  }
}

async function terminateSavedBackendProcesses() {
  let pids;
  try {
    pids = readSavedPids();
  } catch {
    // PID file may not exist or may be partially written.
    return;
  }

  for (const pid of pids) {
    await terminateProcessTree(pid);
  }
}

async function cleanupPreviousRun() {
  try {
    const pids = readSavedPids();
    if (pids.length > 0) {
      console.log(
        `[startE2EStack] Stopping previous backend process trees ${pids.join(
          ', '
        )}`
      );
      for (const pid of pids) {
        await terminateProcessTree(pid);
      }
    }
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
  await sleep(2000);
}

async function waitForBackendUrl(proc, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (proc.exitCode !== null || proc.signalCode !== null) {
      throw new Error(
        `Backend services exited before writing ${urlsPath} (exit code ${proc.exitCode}, signal ${proc.signalCode})`
      );
    }
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

function isRetryableStartupError(error) {
  return !(
    error instanceof Error &&
    error.message.includes('does not contain backend_url')
  );
}

function removeGeneratedFiles() {
  for (const filePath of [urlsPath, pidPath]) {
    try {
      fs.unlinkSync(filePath);
    } catch {
      // file may not exist
    }
  }
}

async function shutdown(exitCode = 0) {
  if (isShuttingDown) {
    return;
  }
  isShuttingDown = true;

  if (viteProc && !viteProc.killed) {
    viteProc.kill('SIGTERM');
  }
  if (serviceProc?.pid) {
    await terminateProcessTree(serviceProc.pid);
  } else if (serviceProc && !serviceProc.killed) {
    serviceProc.kill('SIGTERM');
  }

  try {
    fs.unlinkSync(pidPath);
  } catch {
    // file may not exist
  }

  process.exit(exitCode);
}

process.on('SIGTERM', () => {
  void shutdown(0);
});
process.on('SIGINT', () => {
  void shutdown(0);
});
process.on('exit', () => {
  signalBackendProcess();
});

async function main() {
  await cleanupPreviousRun();

  const serviceArgs = [
    'run',
    'python',
    'scripts/start_e2e_services.py',
    '--dynamic-ports',
    '--output',
    urlsPath,
    '--pid-output',
    pidPath,
  ];
  if (process.env.COVERAGE_E2E_FRONTEND === '1') {
    serviceArgs.push('--coverage');
  }

  const backendUrl = await startBackendServices(serviceArgs);
  serviceProc.on('exit', (code, signal) => {
    if (isShuttingDown) {
      return;
    }
    console.log('[startE2EStack] Backend services exited unexpectedly');
    if (viteProc && !viteProc.killed) {
      viteProc.kill('SIGTERM');
    }
    void shutdown(code ?? (signal ? 1 : 0));
  });

  console.log(`[startE2EStack] backend_url=${backendUrl}`);

  // Run Vite directly via Node so the launcher works on Windows runners where
  // `pnpm` is not on PATH for child processes spawned from the Playwright
  // webServer.  `pnpm dev` is equivalent to `vite --port 3000`.
  const viteBin = path.join(
    frontendRoot,
    'node_modules',
    'vite',
    'bin',
    'vite.js'
  );
  viteProc = spawn('node', [viteBin, '--port', '3000'], {
    cwd: frontendRoot,
    stdio: 'inherit',
    env: {
      ...process.env,
      VITE_PROXY_TARGET: backendUrl,
    },
  });

  viteProc.on('exit', (code, signal) => {
    if (isShuttingDown) {
      return;
    }
    void shutdown(code ?? (signal ? 1 : 0));
  });
}

async function startBackendServices(serviceArgs) {
  const maxAttempts = 3;
  let lastError;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    removeGeneratedFiles();
    console.log(
      `[startE2EStack] Starting backend services (attempt ${attempt}/${maxAttempts})...`
    );

    // Keep backend services in Playwright's process group so webServer teardown
    // can stop them even if this launcher is killed before async cleanup finishes.
    serviceProc = spawn('uv', serviceArgs, {
      cwd: projectRoot,
      stdio: 'inherit',
    });

    try {
      return await waitForBackendUrl(serviceProc);
    } catch (error) {
      lastError = error;
      const retryable = isRetryableStartupError(error);
      console.error(
        `[startE2EStack] Backend services attempt ${attempt} failed`,
        error
      );
      await terminateSavedBackendProcesses();
      if (serviceProc?.pid) {
        await terminateProcessTree(serviceProc.pid);
      }
      serviceProc = undefined;
      removeGeneratedFiles();
      if (!retryable || attempt === maxAttempts) {
        throw error;
      }
      await sleep(2000);
    }
  }

  throw lastError;
}

main().catch(error => {
  console.error('[startE2EStack]', error);
  void shutdown(1);
});
