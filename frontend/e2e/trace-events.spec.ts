/**
 * Trace event integration E2E test.
 *
 * This test drives the real React UI with Playwright, while the existing
 * E2E launcher runs the real backend plus mock LLM and mock device services.
 * The frontend asserts visible debug output; the backend asserts persisted
 * task events and trace artifacts.
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

type CommandAction = {
  action: string;
  [key: string]: unknown;
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

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} was not an object`);
  }
  return value as Record<string, unknown>;
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
    await new Promise(resolve => setTimeout(resolve, 500));
  }

  throw new Error(
    `Task ${taskId} did not reach a terminal status. Latest: ${JSON.stringify(
      latest
    )}`
  );
}

async function waitForTaskEvents(
  request: APIRequestContext,
  backendUrl: string,
  taskId: string,
  requiredEventTypes: string[]
): Promise<TaskEventRecord[]> {
  const deadline = Date.now() + 30000;
  let latestEvents: TaskEventRecord[] = [];

  while (Date.now() < deadline) {
    const response = await request.get(
      `${backendUrl}/api/tasks/${taskId}/events`
    );
    await assertOk(response, 'get task events');
    latestEvents = ((await response.json()) as TaskEventListResponse).events;
    const eventTypes = latestEvents.map(event => event.event_type);
    if (requiredEventTypes.every(type => eventTypes.includes(type))) {
      return latestEvents;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }

  throw new Error(
    `Task ${taskId} did not emit required events ${requiredEventTypes.join(
      ', '
    )}. Latest events: ${latestEvents
      .map(event => event.event_type)
      .join(', ')}`
  );
}

test.describe('Trace debug surface', () => {
  test('shows frontend debug output and persists backend trace events', async ({
    page,
    request,
  }) => {
    const { backend_url, agent_url, llm_url } = readServiceUrls();
    const testDeviceId = 'mock_device_trace_events';

    await assertOk(
      await request.post(`${llm_url}/test/set_responses`, {
        data: [
          '用户要求点击屏幕下方的消息按钮。我看到底部导航栏有消息按钮。do(action="Tap", element=[499,966])',
          '好的，点击成功，进入了消息页面。finish(message="已成功点击消息按钮！")',
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

    await textbox.fill('点击屏幕下方的消息按钮');
    await textbox.press('Meta+Enter');

    const taskResponse = await taskResponsePromise;
    await assertOk(taskResponse, 'submit task');
    const submittedTask = (await taskResponse.json()) as TaskRunResponse;

    await expect(
      page.getByText('点击屏幕下方的消息按钮').first()
    ).toBeVisible();
    await expect(page.getByText('Step 1').first()).toBeVisible({
      timeout: 30000,
    });
    await expect(page.getByText(/^LLM /).first()).toBeVisible({
      timeout: 30000,
    });
    await expect(page.getByText(/^Action /).first()).toBeVisible({
      timeout: 30000,
    });
    await page.getByText('View action').first().click();
    await expect(page.getByText('"action": "Tap"').first()).toBeVisible();
    await expect(
      page.locator('p').filter({ hasText: '已成功点击消息按钮' }).first()
    ).toBeVisible({ timeout: 30000 });

    const finalTask = await waitForTask(request, backend_url, submittedTask.id);
    expect(finalTask.status).toBe('SUCCEEDED');
    expect(finalTask.trace_id).toBeTruthy();
    expect(finalTask.step_count).toBeGreaterThanOrEqual(1);

    const events = await waitForTaskEvents(
      request,
      backend_url,
      submittedTask.id,
      ['status', 'thinking', 'step', 'done', 'trace_summary']
    );
    const eventTypes = events.map(event => event.event_type);
    expect(eventTypes).toContain('status');
    expect(eventTypes).toContain('thinking');
    expect(eventTypes).toContain('step');
    expect(eventTypes).toContain('done');
    expect(eventTypes).toContain('trace_summary');

    const stepEvent = events.find(event => event.event_type === 'step');
    if (!stepEvent) {
      throw new Error('step event not found');
    }
    const action = asRecord(stepEvent.payload.action, 'step action');
    expect(action.action).toBe('Tap');
    const timings = asRecord(stepEvent.payload.timings, 'step timings');
    expect(typeof timings.total_duration_ms).toBe('number');
    expect(typeof timings.llm_duration_ms).toBe('number');
    expect(typeof timings.execute_action_duration_ms).toBe('number');

    const traceSummaryEvent = events.find(
      event => event.event_type === 'trace_summary'
    );
    if (!traceSummaryEvent) {
      throw new Error('trace_summary event not found');
    }
    const summary = asRecord(
      traceSummaryEvent.payload.summary,
      'trace summary'
    );
    expect(summary.trace_id).toBe(finalTask.trace_id);
    expect(summary.steps).toBeGreaterThanOrEqual(1);
    const stepSummaries = traceSummaryEvent.payload.step_summaries;
    expect(Array.isArray(stepSummaries)).toBe(true);
    expect((stepSummaries as unknown[]).length).toBeGreaterThanOrEqual(1);

    const commandResponse = await request.get(
      `${agent_url}/test/commands/actions`
    );
    await assertOk(commandResponse, 'get mock device commands');
    const commands = (await commandResponse.json()) as CommandAction[];
    const commandActions = commands.map(command => command.action);
    expect(commandActions).toContain('screenshot');
    expect(commandActions).toContain('tap');

    const tapCommand = commands.find(command => command.action === 'tap');
    if (!tapCommand) {
      throw new Error(`tap command not found: ${JSON.stringify(commands)}`);
    }
    expect(typeof tapCommand.x).toBe('number');
    expect(typeof tapCommand.y).toBe('number');
  });
});
