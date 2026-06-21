/**
 * Task cancellation / abort regression E2E test — runs against the real app.
 *
 * Drives the classic chat with Playwright while the shared E2E launcher runs
 * the real backend plus mock LLM and mock device services.
 *
 * Covers the user "abort" workflow: a long-running agent task (the mock LLM
 * never calls finish()) must be stoppable from the UI, surface a cancelled
 * message in the conversation, leave the input ready again, and resolve the
 * backend task to status=CANCELLED with a `cancelled` event.
 */
import {
  test,
  expect,
  type APIRequestContext,
  type APIResponse,
} from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

type ServiceUrls = {
  llm_url: string;
  agent_url: string;
  backend_url: string;
  frontend_url: string;
};

type RemoteDeviceAddResponse = {
  success: boolean;
  serial: string;
  message?: string;
  error?: string;
};

type TaskRunResponse = {
  id: string;
  status: string;
  trace_id: string | null;
  step_count: number;
  final_message: string | null;
};

type TaskEventRecord = {
  task_id: string;
  seq: number;
  event_type: string;
  payload: Record<string, unknown>;
};

type TaskEventListResponse = {
  events: TaskEventRecord[];
};

const TERMINAL_STATUSES = new Set([
  'SUCCEEDED',
  'FAILED',
  'CANCELLED',
  'INTERRUPTED',
]);

function readServiceUrls(): ServiceUrls {
  const urlsPath = path.resolve(__dirname, '.service_urls.json');
  if (!fs.existsSync(urlsPath)) {
    throw new Error(
      `.service_urls.json not found - ensure start_e2e_services.py is running`
    );
  }
  return JSON.parse(fs.readFileSync(urlsPath, 'utf-8')) as ServiceUrls;
}

async function assertOk(response: APIResponse, label: string): Promise<void> {
  if (!response.ok()) {
    throw new Error(
      `${label} failed with ${response.status()}: ${await response.text()}`
    );
  }
}

async function waitForTask(
  request: APIRequestContext,
  backendUrl: string,
  taskId: string
): Promise<TaskRunResponse> {
  const deadline = Date.now() + 30000;
  let latest: TaskRunResponse | null = null;

  while (Date.now() < deadline) {
    const response = await request.get(`${backendUrl}/api/tasks/${taskId}`);
    await assertOk(response, 'get task');
    latest = (await response.json()) as TaskRunResponse;
    if (TERMINAL_STATUSES.has(latest.status)) {
      return latest;
    }
    await new Promise(resolve => setTimeout(resolve, 300));
  }

  throw new Error(
    `Task ${taskId} did not reach a terminal status. Latest: ${JSON.stringify(
      latest
    )}`
  );
}

test.describe('Task abort', () => {
  test('cancels a running task from the UI and resolves to CANCELLED', async ({
    page,
    request,
  }) => {
    const { backend_url, agent_url, llm_url } = readServiceUrls();
    // Unique per run so a reused backend (reuseExistingServer in local reruns)
    // never rejects add_remote as "already exists".
    const testDeviceId = `mock_device_abort_${Date.now()}`;

    // Lock the UI to English so button titles / message text are stable.
    await page.addInitScript(() => {
      localStorage.setItem('locale', 'en');
    });

    // A long-running task: the mock LLM keeps issuing taps and never finishes,
    // so the agent stays RUNNING until we abort it.
    await assertOk(
      await request.post(`${llm_url}/test/set_responses`, {
        data: [
          '分析当前界面，需要点击底部消息按钮。do(action="Tap", element=[499,966])',
          '继续观察界面，执行下一步操作。do(action="Tap", element=[200,300])',
          '继续执行任务，再点击一次。do(action="Tap", element=[400,500])',
          '任务还在进行中，继续点击。do(action="Tap", element=[600,700])',
          '继续推进任务。do(action="Tap", element=[100,200])',
        ],
      }),
      'set mock LLM responses'
    );
    await assertOk(
      await request.post(`${llm_url}/test/reset`),
      'reset mock LLM'
    );

    const deviceResponse = await request.post(
      `${backend_url}/api/devices/add_remote`,
      {
        data: { base_url: agent_url, device_id: testDeviceId },
      }
    );
    await assertOk(deviceResponse, 'add remote device');
    const deviceData = (await deviceResponse.json()) as RemoteDeviceAddResponse;
    expect(deviceData.success).toBe(true);
    expect(deviceData.serial).toBeTruthy();

    await assertOk(
      await request.post(`${agent_url}/test/reset`),
      'reset mock device commands'
    );

    await assertOk(
      await request.delete(`${backend_url}/api/config`),
      'clear config'
    );
    await assertOk(
      await request.post(`${backend_url}/api/config`, {
        data: {
          base_url: `${llm_url}/v1`,
          model_name: 'mock-glm-model',
          api_key: 'mock-key',
          agent_type: 'glm-async',
        },
      }),
      'save config'
    );

    await page.goto(
      `/chat?serial=${encodeURIComponent(deviceData.serial)}&mode=classic`
    );

    // The settings dialog may appear on first load — dismiss it.
    const dialog = page.locator('[role="dialog"]');
    if (await dialog.isVisible({ timeout: 3000 }).catch(() => false)) {
      await page.locator('[role="dialog"] button:has-text("Close")').click();
    }

    const textbox = page.locator('textarea');
    await expect(textbox).toBeVisible({ timeout: 15000 });

    // Capture the task id created when the message is submitted.
    const taskResponsePromise = page.waitForResponse(response => {
      return (
        response.request().method() === 'POST' &&
        response.url().includes('/api/task-sessions/') &&
        response.url().endsWith('/tasks')
      );
    });

    await textbox.fill('点击屏幕下方的消息按钮');
    await textbox.press('Meta+Enter');

    const taskResponse = await taskResponsePromise;
    await assertOk(taskResponse, 'submit task');
    const submittedTask = (await taskResponse.json()) as TaskRunResponse;

    // Wait until the task is visibly running: "Step 1" renders in the panel.
    await expect(page.getByText('Step 1').first()).toBeVisible({
      timeout: 30000,
    });

    // The abort button is shown while loading; it carries a stable title.
    const abortButton = page.getByTitle('Abort Chat');
    await expect(abortButton).toBeVisible({ timeout: 5000 });
    await abortButton.click();

    // ── UI assertions ──────────────────────────────────────────────────
    // The cancelled assistant message must surface in the conversation.
    await expect(page.getByText('Task cancelled by user').first()).toBeVisible({
      timeout: 30000,
    });

    // Once loading clears, the abort button disappears and the input is ready.
    await expect(abortButton).toBeHidden({ timeout: 15000 });

    // ── Backend assertions ─────────────────────────────────────────────
    const finalTask = await waitForTask(request, backend_url, submittedTask.id);
    expect(finalTask.status).toBe('CANCELLED');

    const eventsResponse = await request.get(
      `${backend_url}/api/tasks/${submittedTask.id}/events`
    );
    await assertOk(eventsResponse, 'get task events');
    const events = ((await eventsResponse.json()) as TaskEventListResponse)
      .events;
    const eventTypes = events.map(event => event.event_type);
    expect(eventTypes).toContain('cancelled');

    // The agent must have actually executed at least one tap before the abort.
    const commandResponse = await request.get(
      `${agent_url}/test/commands/actions`
    );
    await assertOk(commandResponse, 'get mock device commands');
    const commands = (await commandResponse.json()) as { action: string }[];
    const commandActions = commands.map(command => command.action);
    expect(commandActions).toContain('tap');
  });
});
