/**
 * Regression coverage for issue #376.
 *
 * The selected device should remain available immediately after navigating
 * between chat and history, even if the next /api/devices refresh is slow.
 */
import { test, expect, type APIResponse } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

type ServiceUrls = {
  llm_url: string;
  agent_url: string;
  backend_url: string;
};

type RemoteDeviceAddResponse = {
  success: boolean;
  serial: string | null;
  message?: string;
  error?: string;
};

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

test.describe('Device state routing', () => {
  test('keeps the selected device while navigating to history and back', async ({
    page,
    request,
  }) => {
    const { backend_url, agent_url, llm_url } = readServiceUrls();
    const testDeviceId = `mock_device_issue_376_${Date.now()}`;

    await page.addInitScript(() => {
      localStorage.setItem('locale', 'en');
    });

    const addDeviceResponse = await request.post(
      `${backend_url}/api/devices/add_remote`,
      {
        data: { base_url: agent_url, device_id: testDeviceId },
      }
    );
    await assertOk(addDeviceResponse, 'add remote device');
    const addDeviceData =
      (await addDeviceResponse.json()) as RemoteDeviceAddResponse;
    expect(addDeviceData.success).toBe(true);
    expect(addDeviceData.serial).toBeTruthy();
    const deviceSerial = addDeviceData.serial as string;

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

    let delayDeviceRefresh = false;
    const handleDevicesRoute = async route => {
      if (delayDeviceRefresh) {
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
      const response = await route.fetch();
      await route.fulfill({ response });
    };
    await page.route('**/api/devices', handleDevicesRoute);

    try {
      await page.goto(
        `/chat?serial=${encodeURIComponent(deviceSerial)}&mode=classic`
      );

      await expect(page.locator('textarea')).toBeVisible({ timeout: 15000 });

      delayDeviceRefresh = true;

      await page.locator('nav a[href="/history"]').click();
      await expect(page).toHaveURL(/\/history/);
      await expect(
        page.getByRole('heading', { name: 'Conversation History' })
      ).toBeVisible({ timeout: 1500 });
      await expect(page.getByText(deviceSerial, { exact: true })).toBeVisible({
        timeout: 500,
      });

      await page.locator('nav a[href="/chat"]:has(svg)').click();
      await expect(page).toHaveURL(/\/chat/);

      await expect(page.locator('textarea')).toBeVisible({ timeout: 500 });
    } finally {
      delayDeviceRefresh = false;
      await page.unroute('**/api/devices', handleDevicesRoute);
    }
  });
});
