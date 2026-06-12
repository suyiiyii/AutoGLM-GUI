import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

export const sleep = (ms: number) =>
  new Promise(resolve => setTimeout(resolve, ms));

export async function terminateProcessTree(pid: number) {
  if (!Number.isFinite(pid)) {
    return;
  }

  if (process.platform === 'win32') {
    try {
      await execFileAsync('taskkill', ['/PID', String(pid), '/T', '/F']);
    } catch {
      /* process tree is already gone */
    }
    return;
  }

  try {
    // SIGINT lets uvicorn subprocesses run atexit handlers, which is needed
    // for Python coverage data to be flushed.  Fall back to SIGTERM/SIGKILL.
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
    /* process group is already gone */
  }
}
