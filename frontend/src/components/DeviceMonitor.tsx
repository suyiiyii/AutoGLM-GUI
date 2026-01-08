import React, { useRef, useEffect, useCallback, useState } from 'react';
import { ScrcpyPlayer } from './ScrcpyPlayer';
import { WidthControl } from './WidthControl';
import { ResizableHandle } from './ResizableHandle';
import { useLocalStorage } from '../hooks/useLocalStorage';
import type { ScreenshotResponse } from '../api';
import { getScreenshot } from '../api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { useTranslation } from '../lib/i18n-context';
import {
  Video,
  Image as ImageIcon,
  MonitorPlay,
  ChevronLeft,
  ChevronRight,
  Fingerprint,
  ArrowUpDown,
  AlertCircle,
  CheckCircle2,
  Loader2,
} from 'lucide-react';

interface DeviceMonitorProps {
  deviceId: string;
  serial?: string;
  connectionType?: string;
  isVisible?: boolean;
  className?: string;
}

export function DeviceMonitor({
  deviceId,
  serial: _serial,
  connectionType,
  isVisible = true,
  className = '',
}: DeviceMonitorProps) {
  const t = useTranslation();

  const isRemoteDevice = connectionType === 'remote';
  const [screenshot, setScreenshot] = useState<ScreenshotResponse | null>(null);
  const [useVideoStream, setUseVideoStream] = useState(!isRemoteDevice);
  const [videoStreamFailed, setVideoStreamFailed] = useState(false);
  const [displayMode, setDisplayMode] = useState<
    'auto' | 'video' | 'screenshot'
  >(isRemoteDevice ? 'screenshot' : 'auto');
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [feedbackType, setFeedbackType] = useState<
    'tap' | 'swipe' | 'error' | 'success'
  >('success');
  const [showControlArea, setShowControlArea] = useState(false);
  const [showControls, setShowControls] = useState(false);
  const [panelWidth, setPanelWidth] = useLocalStorage<number | 'auto'>(
    'device-monitor-width',
    320
  );

  const videoStreamRef = useRef<{ close: () => void } | null>(null);
  const screenshotFetchingRef = useRef(false);
  const feedbackTimeoutRef = useRef<number | null>(null);
  const controlsTimeoutRef = useRef<number | null>(null);

  const showFeedback = (
    message: string,
    duration = 2000,
    type: 'tap' | 'swipe' | 'error' | 'success' = 'success'
  ) => {
    if (feedbackTimeoutRef.current) {
      clearTimeout(feedbackTimeoutRef.current);
    }
    setFeedbackType(type);
    setFeedbackMessage(message);
    feedbackTimeoutRef.current = setTimeout(() => {
      setFeedbackMessage(null);
    }, duration);
  };

  const handleMouseEnter = () => {
    if (controlsTimeoutRef.current) {
      clearTimeout(controlsTimeoutRef.current);
    }
    setShowControlArea(true);
  };

  const handleMouseLeave = () => {
    controlsTimeoutRef.current = setTimeout(() => {
      setShowControlArea(false);
    }, 500);
  };

  const toggleControls = () => {
    setShowControls(prev => !prev);
  };

  const handleWidthChange = (width: number | 'auto') => {
    setPanelWidth(width);
  };

  const handleResize = (deltaX: number) => {
    if (typeof panelWidth !== 'number') return;
    const newWidth = Math.min(640, Math.max(240, panelWidth + deltaX));
    setPanelWidth(newWidth);
  };

  const handleVideoStreamReady = useCallback(
    (stream: { close: () => void } | null) => {
      videoStreamRef.current = stream;
    },
    []
  );

  const handleFallback = useCallback(() => {
    setVideoStreamFailed(true);
    setUseVideoStream(false);
  }, []);

  const toggleDisplayMode = (mode: 'auto' | 'video' | 'screenshot') => {
    setDisplayMode(mode);
  };

  useEffect(() => {
    return () => {
      if (feedbackTimeoutRef.current) {
        clearTimeout(feedbackTimeoutRef.current);
      }
      if (controlsTimeoutRef.current) {
        clearTimeout(controlsTimeoutRef.current);
      }
      if (videoStreamRef.current) {
        videoStreamRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    if (!deviceId || !isVisible) return;

    const shouldPollScreenshots =
      displayMode === 'screenshot' ||
      (displayMode === 'auto' && videoStreamFailed);

    if (!shouldPollScreenshots) {
      return;
    }

    const fetchScreenshot = async () => {
      if (screenshotFetchingRef.current) return;

      screenshotFetchingRef.current = true;
      try {
        const data = await getScreenshot(deviceId);
        if (data.success) {
          setScreenshot(data);
        }
      } catch (e) {
        console.error('Failed to fetch screenshot:', e);
      } finally {
        screenshotFetchingRef.current = false;
      }
    };

    fetchScreenshot();
    const interval = setInterval(fetchScreenshot, 500);

    return () => clearInterval(interval);
  }, [deviceId, videoStreamFailed, displayMode, isVisible]);

  const widthStyle =
    typeof panelWidth === 'number' ? `${panelWidth}px` : 'auto';

  return (
    <Card
      className={`flex-shrink-0 relative min-h-0 overflow-hidden bg-background ${className}`}
      style={{
        width: widthStyle,
        minWidth: typeof panelWidth === 'number' ? undefined : '240px',
        maxWidth: typeof panelWidth === 'number' ? undefined : '640px',
      }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Resizable handle - left edge */}
      {typeof panelWidth === 'number' && (
        <ResizableHandle
          onResize={handleResize}
          minWidth={240}
          maxWidth={640}
          className="z-20"
        />
      )}
      {/* Toggle and controls - shown on hover */}
      <div
        className={`absolute top-4 right-4 z-10 transition-opacity duration-200 ${
          showControlArea ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
      >
        <div className="flex items-start gap-2">
          {/* Combined controls container - both controls slide together */}
          <div
            className={`flex flex-col items-end gap-2 transition-all duration-300 ${
              showControls
                ? 'opacity-100 translate-x-0'
                : 'opacity-0 translate-x-4 pointer-events-none'
            }`}
          >
            {/* Display mode controls */}
            <div className="flex items-center gap-1 bg-popover/90 backdrop-blur rounded-xl p-1 shadow-lg border border-border">
              {!isRemoteDevice && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleDisplayMode('auto')}
                  className={`h-7 px-3 text-xs rounded-lg transition-colors ${
                    displayMode === 'auto'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-foreground hover:bg-accent hover:text-accent-foreground'
                  }`}
                >
                  {t.devicePanel?.auto || 'Auto'}
                </Button>
              )}
              {!isRemoteDevice && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleDisplayMode('video')}
                  className={`h-7 px-3 text-xs rounded-lg transition-colors ${
                    displayMode === 'video'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-foreground hover:bg-accent hover:text-accent-foreground'
                  }`}
                >
                  <Video className="w-3 h-3 mr-1" />
                  {t.devicePanel?.video || 'Video'}
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => toggleDisplayMode('screenshot')}
                className={`h-7 px-3 text-xs rounded-lg transition-colors ${
                  displayMode === 'screenshot'
                    ? 'bg-primary text-primary-foreground'
                    : 'text-foreground hover:bg-accent hover:text-accent-foreground'
                }`}
              >
                <ImageIcon className="w-3 h-3 mr-1" />
                {t.devicePanel?.image || 'Image'}
              </Button>
            </div>

            {/* Width controls - aligned with display mode controls */}
            <WidthControl
              currentWidth={panelWidth}
              onWidthChange={handleWidthChange}
            />
          </div>

          {/* Toggle button - always visible in top-right */}
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleControls}
            className="h-8 w-8 rounded-full bg-popover/90 backdrop-blur border border-border shadow-lg hover:bg-accent"
            title={showControls ? 'Hide controls' : 'Show controls'}
          >
            {showControls ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </Button>
        </div>
      </div>

      {/* Current mode indicator - bottom left */}
      <div className="absolute bottom-4 left-4 z-10">
        <Badge
          variant="secondary"
          className="bg-white/90 text-slate-700 border border-slate-200 dark:bg-slate-900/90 dark:text-slate-300 dark:border-slate-700"
        >
          {displayMode === 'auto' && (t.devicePanel?.auto || 'Auto')}
          {displayMode === 'video' && (
            <>
              <MonitorPlay className="w-3 h-3 mr-1" />
              {t.devicePanel?.video || 'Video'}
            </>
          )}
          {displayMode === 'screenshot' && (
            <>
              <ImageIcon className="w-3 h-3 mr-1" />
              {t.devicePanel?.imageRefresh || 'Screenshot'}
            </>
          )}
        </Badge>
      </div>

      {/* Feedback message */}
      {feedbackMessage && (
        <div className="absolute bottom-4 right-4 z-20 flex items-center gap-2 px-3 py-2 bg-[#1d9bf0] text-white text-sm rounded-xl shadow-lg">
          {feedbackType === 'error' && <AlertCircle className="w-4 h-4" />}
          {feedbackType === 'tap' && <Fingerprint className="w-4 h-4" />}
          {feedbackType === 'swipe' && <ArrowUpDown className="w-4 h-4" />}
          {feedbackType === 'success' && <CheckCircle2 className="w-4 h-4" />}
          <span>{feedbackMessage}</span>
        </div>
      )}

      {/* Video stream */}
      {displayMode === 'video' ||
      (displayMode === 'auto' && useVideoStream && !videoStreamFailed) ? (
        <ScrcpyPlayer
          deviceId={deviceId}
          className="w-full h-full"
          enableControl={true}
          onFallback={handleFallback}
          onTapSuccess={() =>
            showFeedback(t.devicePanel?.tapped || 'Tapped', 2000, 'tap')
          }
          onTapError={error =>
            showFeedback(
              (t.devicePanel?.tapError || 'Tap error: {error}').replace(
                '{error}',
                error
              ),
              3000,
              'error'
            )
          }
          onSwipeSuccess={() =>
            showFeedback(t.devicePanel?.swiped || 'Swiped', 2000, 'swipe')
          }
          onSwipeError={error =>
            showFeedback(
              (t.devicePanel?.swipeError || 'Swipe error: {error}').replace(
                '{error}',
                error
              ),
              3000,
              'error'
            )
          }
          onStreamReady={handleVideoStreamReady}
          fallbackTimeout={10000}
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-muted/30 min-h-0">
          {screenshot && screenshot.success ? (
            <div className="relative w-full h-full flex items-center justify-center min-h-0">
              <img
                src={`data:image/png;base64,${screenshot.image}`}
                alt="Device Screenshot"
                className="max-w-full max-h-full object-contain"
                style={{
                  width: screenshot.width > screenshot.height ? '100%' : 'auto',
                  height:
                    screenshot.width > screenshot.height ? 'auto' : '100%',
                }}
              />
              {screenshot.is_sensitive && (
                <div className="absolute top-12 right-2 px-2 py-1 bg-yellow-500 text-white text-xs rounded-lg">
                  {t.devicePanel?.sensitiveContent || 'Sensitive Content'}
                </div>
              )}
            </div>
          ) : screenshot?.error ? (
            <div className="text-center text-destructive">
              <AlertCircle className="w-8 h-8 mx-auto mb-2" />
              <p className="font-medium">
                {t.devicePanel?.screenshotFailed || 'Screenshot Failed'}
              </p>
              <p className="text-xs mt-1 opacity-60">{screenshot.error}</p>
            </div>
          ) : (
            <div className="text-center text-muted-foreground">
              <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin" />
              <p className="text-sm">
                {t.devicePanel?.loading || 'Loading...'}
              </p>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
