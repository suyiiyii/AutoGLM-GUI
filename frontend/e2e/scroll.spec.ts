/**
 * Auto-scroll regression E2E test — runs against the real React app.
 *
 * Requires the backend services (mock LLM + mock agent + AutoGLM-GUI)
 * to be running.  The Playwright config starts them via
 * scripts/start_e2e_services.py.
 *
 * Covers issue #346: in classic mode (DevicePanel) the chat must stay pinned
 * to the latest message while the agent streams its response, as long as the
 * user has not scrolled up.  DevicePanel renders its messages inside a Radix
 * <ScrollArea>, so the scrollable element is the viewport node.
 */
import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Type-safe window extensions used by the scroll observer injected via page.evaluate
declare global {
  interface Window {
    __scrollReport: { maxDistance: number; samples: number[]; error?: string };
    __scrollReportStop?: () => void;
    __scrollObserver?: MutationObserver;
  }
}

// The DevicePanel <ScrollArea> roots carry this test id; the element that
// actually scrolls is the Radix viewport nested inside it.
const VIEWPORT_SELECTOR =
  '[data-testid="chat-scroll-container"] [data-slot="scroll-area-viewport"]';

function readServiceUrls(): { backend_url: string; agent_url: string } {
  const urlsPath = path.resolve(__dirname, '.service_urls.json');
  if (!fs.existsSync(urlsPath)) {
    throw new Error(
      `.service_urls.json not found — ensure start_e2e_services.py is running`
    );
  }
  return JSON.parse(fs.readFileSync(urlsPath, 'utf-8'));
}

test.describe('DevicePanel auto-scroll', () => {
  test('stays at bottom during streaming agent response', async ({
    page,
    request,
  }) => {
    const { backend_url, agent_url } = readServiceUrls();

    // ── 1. Configure backend (device + LLM config) ──────────────────────

    // Register mock device
    const deviceRes = await request.post(
      `${backend_url}/api/devices/add_remote`,
      {
        data: { base_url: agent_url, device_id: 'mock_device_001' },
      }
    );
    expect(deviceRes.status()).toBe(200);
    const deviceData = await deviceRes.json();
    expect(deviceData.success).toBe(true);
    const deviceSerial = deviceData.serial;

    // Configure LLM via config API
    await request.delete(`${backend_url}/api/config`);
    const configRes = await request.post(`${backend_url}/api/config`, {
      data: {
        base_url: 'http://localhost:18003/v1',
        model_name: 'mock-glm-model',
        api_key: 'mock-key',
        agent_type: 'glm-async',
      },
    });
    expect(configRes.status()).toBe(200);

    // Set multiple mock LLM responses so the agent produces enough content
    // to overflow the scroll container (5 steps ≈ plenty of scrolling needed)
    await request.post('http://localhost:18003/test/set_responses', {
      data: [
        '用户要求点击屏幕下方的消息按钮。我看到底部导航栏有消息按钮。do(action="Tap", element=[499,966])',
        '好的，点击成功，进入了消息页面。finish(message="已成功点击消息按钮！")',
        '用户说再看看订单。我看到页面上有订单选项。do(action="Tap", element=[300,500])',
        '进入了订单页面。finish(message="已进入订单页面")',
        '所有任务已完成。finish(message="任务完成")',
      ],
    });
    await request.post('http://localhost:18003/test/reset');

    // ── 2. Navigate to frontend ─────────────────────────────────────────

    // Use a smaller viewport so chat content overflows the scroll container.
    // If content fits without scrolling, the auto-scroll test is meaningless.
    await page.setViewportSize({ width: 1280, height: 500 });

    await page.goto(
      `/chat?serial=${encodeURIComponent(deviceSerial)}&mode=classic`
    );

    // The settings dialog may appear — close it first
    const dialog = page.locator('[role="dialog"]');
    if (await dialog.isVisible({ timeout: 3000 }).catch(() => false)) {
      await page.locator('[role="dialog"] button:has-text("Close")').click();
      await page.waitForTimeout(500);
    }

    // Wait for the textarea (chat input) to appear
    const textbox = page.locator('textarea');
    await expect(textbox).toBeVisible({ timeout: 15000 });

    // The Radix ScrollArea viewport should exist before we start tracking.
    await page.waitForSelector(VIEWPORT_SELECTOR, { timeout: 15000 });

    // ── 3. Set up scroll tracking ───────────────────────────────────────

    // Inject a scroll observer that records the distance from bottom over time.
    // We read it back after streaming completes.
    await page.evaluate(viewportSelector => {
      window.__scrollReport = {
        maxDistance: 0,
        samples: [] as number[],
      };

      const viewport = document.querySelector(
        viewportSelector
      ) as HTMLDivElement | null;
      if (!viewport) {
        window.__scrollReport.error = 'No scroll viewport found';
        return;
      }

      const record = () => {
        const d =
          viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
        window.__scrollReport.maxDistance = Math.max(
          window.__scrollReport.maxDistance,
          d
        );
        window.__scrollReport.samples.push(Math.round(d));
      };

      // Poll scroll position every 100ms
      const interval = setInterval(record, 100);
      window.__scrollReportStop = () => clearInterval(interval);

      // Also observe DOM changes to detect new messages
      const observer = new MutationObserver(record);
      observer.observe(viewport, {
        childList: true,
        subtree: true,
        characterData: true,
      });
      window.__scrollObserver = observer;
    }, VIEWPORT_SELECTOR);

    // ── 4. Send a message ───────────────────────────────────────────────

    await textbox.fill('点击屏幕下方的消息按钮');
    await textbox.press('Meta+Enter');

    // ── 5. Wait for streaming to complete ────────────────────────────────

    // The agent will stream thinking → step → done events.
    await page.waitForTimeout(2000);

    // Wait for the loading spinner to disappear (agent finished)
    const loadingIndicator = page.locator('.animate-spin');
    await loadingIndicator
      .first()
      .waitFor({ state: 'hidden', timeout: 60000 })
      .catch(() => {
        // May have already disappeared
      });

    // Extra wait to let all DOM updates + scroll effects (incl. async
    // screenshot loads and the ResizeObserver re-pin) settle.
    await page.waitForTimeout(1500);

    // ── 6. Read scroll report and verify ────────────────────────────────

    const report = await page.evaluate(() => {
      const r = window.__scrollReport;
      window.__scrollReportStop?.();
      window.__scrollObserver?.disconnect();
      return r;
    });

    console.log('Scroll report:', JSON.stringify(report));

    if (report.error) {
      throw new Error(report.error);
    }

    // Verify the viewport is the real scroll container (content > viewport).
    // If this fails, the layout is broken (the bug also reported as "missing
    // scrollbar") or the test viewport is too tall — reduce height further.
    const overflow = await page.evaluate(viewportSelector => {
      const v = document.querySelector(
        viewportSelector
      ) as HTMLDivElement | null;
      return v
        ? {
            scrollHeight: v.scrollHeight,
            clientHeight: v.clientHeight,
            distanceFromBottom: v.scrollHeight - v.scrollTop - v.clientHeight,
            hasOverflow: v.scrollHeight > v.clientHeight,
          }
        : null;
    }, VIEWPORT_SELECTOR);
    console.log('Viewport state:', JSON.stringify(overflow));
    if (!overflow) {
      throw new Error('scroll viewport not found after streaming');
    }
    expect(overflow.hasOverflow).toBe(true);

    // Verify we actually collected data (streaming produced DOM changes).
    expect(report.samples.length).toBeGreaterThan(0);

    // The chat must never have fallen a full screen behind the latest message
    // while the user was parked at the bottom.
    expect(report.maxDistance).toBeLessThan(overflow.clientHeight);

    // And once everything settled, it must be pinned to the very bottom.
    // Allow a few px for sub-pixel rounding.
    expect(overflow.distanceFromBottom).toBeLessThanOrEqual(5);
  });
});
