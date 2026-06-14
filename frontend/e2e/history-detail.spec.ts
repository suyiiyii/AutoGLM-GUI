/**
 * Conversation history detail E2E test — runs against the real app.
 *
 * Covers the post-task history workflow from a user's point of view: after a
 * task completes in the classic chat, the user opens the History page, sees
 * the run, and drills into the detail dialog to inspect the task, the steps,
 * and the per-step timing chips.
 *
 * The shared E2E launcher provides the real backend plus mock LLM and mock
 * device services.
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

const INSTRUCTION = '点击屏幕下方的消息按钮';

test.describe('History detail', () => {
  test('lists a finished classic run and opens its step-by-step detail', async ({
    page,
    request,
  }) => {
    const { backend_url, agent_url, llm_url } = readServiceUrls();
    // Unique per run so a reused backend (reuseExistingServer in local reruns)
    // never rejects add_remote as "already exists".
    const testDeviceId = `mock_device_history_${Date.now()}`;

    // Lock the UI to English for stable assertions.
    await page.addInitScript(() => {
      localStorage.setItem('locale', 'en');
    });

    // A single-step successful task: one tap, then finish.
    await assertOk(
      await request.post(`${llm_url}/test/set_responses`, {
        data: [
          '分析界面，点击底部消息按钮。do(action="Tap", element=[499,966])',
          '已进入消息页面。finish(message="已成功点击消息按钮！")',
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

    // ── 1. Run a task in the classic chat ──────────────────────────────
    await page.goto(
      `/chat?serial=${encodeURIComponent(deviceData.serial)}&mode=classic`
    );

    const dialog = page.locator('[role="dialog"]');
    if (await dialog.isVisible({ timeout: 3000 }).catch(() => false)) {
      await page.locator('[role="dialog"] button:has-text("Close")').click();
    }

    const textbox = page.locator('textarea');
    await expect(textbox).toBeVisible({ timeout: 15000 });

    const taskResponsePromise = page.waitForResponse(response => {
      return (
        response.request().method() === 'POST' &&
        response.url().includes('/api/task-sessions/') &&
        response.url().endsWith('/tasks')
      );
    });

    await textbox.fill(INSTRUCTION);
    await textbox.press('Meta+Enter');

    const taskResponse = await taskResponsePromise;
    await assertOk(taskResponse, 'submit task');
    const submittedTask = (await taskResponse.json()) as TaskRunResponse;

    // Wait for the run to finish in the backend, then for the UI to clear its
    // loading state (abort button hidden => input ready again). Asserting the
    // final message text directly is fragile — it also matches the hidden
    // JSON action-details block — so we gate on backend + loading state.
    await waitForTask(request, backend_url, submittedTask.id);
    await expect(page.getByTitle('Abort Chat')).toBeHidden({ timeout: 30000 });

    // ── 2. Navigate to history ─────────────────────────────────────────
    await page.locator('nav a[href="/history"]').click();
    await expect(page).toHaveURL(/\/history/);
    await expect(
      page.getByRole('heading', { name: 'Conversation History' })
    ).toBeVisible({ timeout: 10000 });

    // The finished run must appear in the list.
    const card = page
      .locator('[data-testid="history-record-card"]', { hasText: INSTRUCTION })
      .first();
    await expect(card).toBeVisible({ timeout: 10000 });

    // ── 3. Open the detail dialog ──────────────────────────────────────
    // The Eye button is the per-record "view detail" affordance, scoped to
    // this record's card via a stable data-testid (not Tailwind classes).
    const detailButton = card.getByRole('button', {
      name: 'Conversation Detail',
    });
    await detailButton.click();

    await expect(
      page.getByRole('heading', { name: 'Conversation Detail' })
    ).toBeVisible({ timeout: 5000 });

    // Task label + the instruction text render inside the dialog.
    await expect(
      page.locator('[role="dialog"]').getByText('Task').first()
    ).toBeVisible();
    await expect(
      page.locator('[role="dialog"]').getByText(INSTRUCTION).first()
    ).toBeVisible();

    // Step 1 is expanded by default and shows per-step timing chips.
    await expect(
      page.locator('[role="dialog"]').getByText('Step 1').first()
    ).toBeVisible();
    await expect(
      page.locator('[role="dialog"]').getByText('Total').first()
    ).toBeVisible();
    await expect(
      page.locator('[role="dialog"]').getByText('Model').first()
    ).toBeVisible();

    // The tap action recorded by the agent surfaces in the Action block.
    await expect(
      page.locator('[role="dialog"]').getByText('"action": "Tap"').first()
    ).toBeVisible();

    // The success result message also renders in the detail view.
    await expect(
      page.locator('[role="dialog"]').getByText('已成功点击消息按钮').first()
    ).toBeVisible();
  });
});
