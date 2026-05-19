import { spawn, execFile } from 'child_process';
import console from 'console';
import fs from 'fs';
import path from 'path';
import process from 'process';
import { promisify } from 'util';
import { fileURLToPath, URL } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const frontendRoot = path.resolve(__dirname, '..');
const projectRoot = path.resolve(frontendRoot, '..');
const urlsPath = path.resolve(__dirname, '.service_urls.json');
const pidPath = path.resolve(__dirname, '.service_pids.json');

const sleep = ms => new Promise(resolve => globalThis.setTimeout(resolve, ms));
const execFileAsync = promisify(execFile);
function parseFrontendPort() {
  const portFlagIndex = process.argv.indexOf('--frontend-port');
  if (portFlagIndex >= 0) {
    const explicitPort = Number(process.argv[portFlagIndex + 1]);
    if (Number.isFinite(explicitPort)) {
      return explicitPort;
    }
  }

  return Number(process.env.PLAYWRIGHT_FRONTEND_PORT || '3000');
}

const frontendPort = parseFrontendPort();

function readServiceUrls() {
  try {
    return JSON.parse(fs.readFileSync(urlsPath, 'utf-8'));
  } catch {
    return null;
  }
}

async function waitForBackend(urlsDeadlineMs) {
  while (Date.now() < urlsDeadlineMs) {
    const urls = readServiceUrls();
    if (!urls?.backend_url) {
      await sleep(250);
      continue;
    }

    try {
      const response = await globalThis.fetch(`${urls.backend_url}/api/health`);
      if (response.ok) {
        return urls;
      }
    } catch {
      // Service still booting.
    }
    await sleep(250);
  }

  throw new Error('Timed out waiting for backend service URLs / health check');
}

function spawnDetached(command, args, options) {
  const child = spawn(command, args, {
    ...options,
    detached: true,
    stdio: 'inherit',
  });
  child.unref();
  return child;
}

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
    const payload = JSON.parse(fs.readFileSync(pidPath, 'utf-8'));
    for (const pid of [payload.vitePid, payload.servicePid]) {
      await terminateProcessTree(pid);
    }
  } catch {
    // no previous pid file
  }

  for (const filePath of [urlsPath, pidPath]) {
    try {
      fs.unlinkSync(filePath);
    } catch {
      // file may not exist
    }
  }
}

async function main() {
  await cleanupPreviousRun();

  let serviceProc = null;
  let viteProc = null;
  let shuttingDown = false;

  const cleanupProcesses = async () => {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    await terminateProcessTree(viteProc?.pid);
    await terminateProcessTree(serviceProc?.pid);
  };

  const handleTermination = () => {
    void cleanupProcesses().finally(() => process.exit(0));
  };

  try {
    process.once('SIGTERM', handleTermination);
    process.once('SIGINT', handleTermination);

    serviceProc = spawnDetached(
      'uv',
      [
        'run',
        'python',
        'scripts/start_e2e_services.py',
        '--dynamic-ports',
        '--frontend-port',
        String(frontendPort),
        '--output',
        urlsPath,
      ],
      { cwd: projectRoot }
    );

    const urls = await waitForBackend(Date.now() + 30000);
    const frontendUrl = new URL(urls.frontend_url);

    viteProc = spawnDetached(
      'pnpm',
      ['exec', 'vite', '--host', '127.0.0.1', '--port', frontendUrl.port],
      {
        cwd: frontendRoot,
        env: {
          ...process.env,
          VITE_PROXY_TARGET: urls.backend_url,
        },
      }
    );

    fs.writeFileSync(
      pidPath,
      JSON.stringify(
        {
          servicePid: serviceProc.pid,
          vitePid: viteProc.pid,
        },
        null,
        2
      )
    );

    await new Promise((resolve, reject) => {
      const onExit = (name, code, signal) => {
        reject(
          new Error(
            `${name} exited unexpectedly (code=${code ?? 'null'}, signal=${signal ?? 'null'})`
          )
        );
      };

      serviceProc.once('exit', (code, signal) =>
        onExit('service launcher', code, signal)
      );
      viteProc.once('exit', (code, signal) =>
        onExit('vite dev server', code, signal)
      );
    });
  } finally {
    process.off('SIGTERM', handleTermination);
    process.off('SIGINT', handleTermination);
    await cleanupProcesses();
  }
}

main().catch(error => {
  console.error('[startPlaywrightWebServer]', error);
  process.exit(1);
});
