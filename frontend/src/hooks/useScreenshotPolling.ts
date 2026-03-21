import { useEffect, useRef, useState } from 'react';
import { getScreenshot, type ScreenshotResponse } from '../api';
import { usePageVisibility } from './usePageVisibility';

interface UseScreenshotPollingOptions {
  deviceId: string;
  enabled: boolean;
  pollDelayMs: number;
}

interface UseScreenshotPollingResult {
  screenshot: ScreenshotResponse | null;
}

export function useScreenshotPolling({
  deviceId,
  enabled,
  pollDelayMs,
}: UseScreenshotPollingOptions): UseScreenshotPollingResult {
  const isPageVisible = usePageVisibility();
  const [screenshot, setScreenshot] = useState<ScreenshotResponse | null>(null);
  const isFetchingRef = useRef(false);

  useEffect(() => {
    if (!deviceId || !enabled || !isPageVisible) {
      return;
    }

    let isCancelled = false;
    let timeoutId: number | null = null;

    const fetchScreenshot = async () => {
      if (isFetchingRef.current || isCancelled) {
        return;
      }

      isFetchingRef.current = true;
      try {
        const data = await getScreenshot(deviceId);
        if (!isCancelled && data.success) {
          setScreenshot(data);
        }
      } catch (error) {
        if (!isCancelled) {
          console.error('Failed to fetch screenshot:', error);
        }
      } finally {
        isFetchingRef.current = false;
      }
    };

    const pollScreenshots = async () => {
      await fetchScreenshot();

      if (isCancelled) {
        return;
      }

      timeoutId = window.setTimeout(() => {
        void pollScreenshots();
      }, pollDelayMs);
    };

    void pollScreenshots();

    return () => {
      isCancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [deviceId, enabled, isPageVisible, pollDelayMs]);

  return { screenshot };
}
