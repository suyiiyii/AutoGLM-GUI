import { useEffect, useRef, useState } from 'react';
import React from 'react';
import jMuxer from 'jmuxer';
import JMuxer from 'jmuxer';
import {
  sendTap,
  sendSwipe,
  getScreenshot,
  sendTouchDown,
  sendTouchMove,
  sendTouchUp,
} from '../api';
const WHEEL_DELAY_MS = 400; // Debounce delay for wheel events
const MOTION_THROTTLE_MS = 50; // Throttle for motion events (50ms = 20 events/sec)
interface ScrcpyPlayerProps {
  deviceId: string; // 设备 ID（必填）
  className?: string;
  onFallback?: () => void; // Callback when fallback to screenshot is needed
  fallbackTimeout?: number; // Timeout in ms before fallback (default 5000)
  enableControl?: boolean; // Enable click control
  onTapSuccess?: () => void; // Callback on successful tap
  onTapError?: (error: string) => void; // Callback on tap error
  onSwipeSuccess?: () => void; // Callback on successful swipe
  onSwipeError?: (error: string) => void; // Callback on swipe error
  onStreamReady?: (stream: { close: () => void } | null) => void; // Callback when video stream is ready
}

export function ScrcpyPlayer({
  deviceId,
  className,
  onFallback,
  fallbackTimeout = 5000,
  enableControl = false,
  onTapSuccess,
  onTapError,
  onSwipeSuccess,
  onSwipeError,
  onStreamReady,
}: ScrcpyPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const jmuxerRef = useRef<JMuxer | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const deviceIdRef = useRef<string>(deviceId); // Store current deviceId for reconnect logic
  const [status, setStatus] = useState<
    'connecting' | 'connected' | 'error' | 'disconnected'
  >('connecting');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fallbackTimerRef = useRef<NodeJS.Timeout | null>(null);
  const hasReceivedDataRef = useRef(false);

  // Ripple effect state
  interface RippleEffect {
    id: number;
    x: number; // CSS pixel coordinates
    y: number;
  }
  const [ripples, setRipples] = useState<RippleEffect[]>([]);

  // Swipe detection state
  const isDraggingRef = useRef(false);
  const dragStartRef = useRef<{ x: number; y: number; time: number } | null>(
    null
  );
  const [swipeLine, setSwipeLine] = useState<{
    id: number;
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  } | null>(null);

  // Wheel debounce state
  const wheelTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const accumulatedScrollRef = useRef<{
    deltaY: number;
    lastTime: number;
    mouseX: number;
    mouseY: number;
  } | null>(null);

  // Motion event throttling state
  const lastMoveTimeRef = useRef<number>(0);
  const pendingMoveRef = useRef<{ x: number; y: number } | null>(null);
  const moveThrottleTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Device actual resolution (not video stream resolution)
  const [deviceResolution, setDeviceResolution] = useState<{
    width: number;
    height: number;
  } | null>(null);

  // Latency monitoring
  const frameCountRef = useRef(0);
  const lastStatsTimeRef = useRef<number>(0);

  // Error recovery tracking
  const lastErrorTimeRef = useRef<number>(0);
  const lastConnectTimeRef = useRef<number>(0);
  const resetAttemptsRef = useRef<number>(0); // Track consecutive reset attempts
  const lastResetTimeRef = useRef<number>(0); // Track last reset time for debouncing
  const MAX_RESET_ATTEMPTS = 3; // Max reset attempts before full reconnect
  const RESET_DEBOUNCE_MS = 1000; // Minimum time between resets

  // Use ref to store latest callback to avoid useEffect re-running
  const onFallbackRef = useRef(onFallback);
  const fallbackTimeoutRef = useRef(fallbackTimeout);
  const onStreamReadyRef = useRef(onStreamReady);

  /**
   * Convert click coordinates to device coordinates
   * Accounts for object-fit: contain letterboxing
   */
  const getDeviceCoordinates = (
    clickX: number,
    clickY: number,
    videoElement: HTMLVideoElement
  ): { x: number; y: number } | null => {
    // Get video element's display dimensions
    const rect = videoElement.getBoundingClientRect();
    const displayWidth = rect.width;
    const displayHeight = rect.height;

    // Get video's native dimensions
    const videoWidth = videoElement.videoWidth;
    const videoHeight = videoElement.videoHeight;

    if (videoWidth === 0 || videoHeight === 0) {
      console.warn('[ScrcpyPlayer] Video dimensions not available yet');
      return null;
    }

    // Calculate aspect ratios
    const videoAspect = videoWidth / videoHeight;
    const displayAspect = displayWidth / displayHeight;

    // Calculate actual rendered video dimensions (accounting for object-fit: contain)
    let renderedWidth: number;
    let renderedHeight: number;
    let offsetX: number;
    let offsetY: number;

    if (displayAspect > videoAspect) {
      // Display is wider - letterbox on sides
      renderedHeight = displayHeight;
      renderedWidth = videoAspect * displayHeight;
      offsetX = (displayWidth - renderedWidth) / 2;
      offsetY = 0;
    } else {
      // Display is taller - letterbox on top/bottom
      renderedWidth = displayWidth;
      renderedHeight = displayWidth / videoAspect;
      offsetX = 0;
      offsetY = (displayHeight - renderedHeight) / 2;
    }

    // Check if click is within rendered video area
    const relativeX = clickX - offsetX;
    const relativeY = clickY - offsetY;

    if (
      relativeX < 0 ||
      relativeX > renderedWidth ||
      relativeY < 0 ||
      relativeY > renderedHeight
    ) {
      console.warn('[ScrcpyPlayer] Click outside video area (in letterbox)');
      return null;
    }

    // Convert to device coordinates
    const deviceX = Math.round((relativeX / renderedWidth) * videoWidth);
    const deviceY = Math.round((relativeY / renderedHeight) * videoHeight);

    console.log(`[ScrcpyPlayer] Coordinate transform:
      Click: (${clickX}, ${clickY})
      Display: ${displayWidth}x${displayHeight}
      Video: ${videoWidth}x${videoHeight}
      Rendered: ${renderedWidth}x${renderedHeight} at offset (${offsetX}, ${offsetY})
      Device: (${deviceX}, ${deviceY})`);

    return { x: deviceX, y: deviceY };
  };

  /**
   * Handle mouse down event for drag start
   */
  const handleMouseDown = async (event: React.MouseEvent<HTMLVideoElement>) => {
    if (!enableControl || !videoRef.current || status !== 'connected') return;

    isDraggingRef.current = true;
    dragStartRef.current = {
      x: event.clientX,
      y: event.clientY,
      time: Date.now(),
    };

    // Convert to device coordinates and send DOWN event
    const rect = videoRef.current.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    const deviceCoords = getDeviceCoordinates(clickX, clickY, videoRef.current);
    if (!deviceCoords || !deviceResolution) return;

    // Scale to actual device resolution
    const videoWidth = videoRef.current.videoWidth;
    const videoHeight = videoRef.current.videoHeight;
    const scaleX = deviceResolution.width / videoWidth;
    const scaleY = deviceResolution.height / videoHeight;

    const actualDeviceX = Math.round(deviceCoords.x * scaleX);
    const actualDeviceY = Math.round(deviceCoords.y * scaleY);

    try {
      await sendTouchDown(actualDeviceX, actualDeviceY, deviceId);
      console.log(
        `[Touch] DOWN: (${actualDeviceX}, ${actualDeviceY}) for device ${deviceId}`
      );
    } catch (error) {
      console.error('[Touch] DOWN failed:', error);
    }
  };

  /**
   * Handle mouse move event with throttling for real-time dragging
   */
  const handleMouseMove = (event: React.MouseEvent<HTMLVideoElement>) => {
    if (!isDraggingRef.current || !dragStartRef.current) return;

    // Update swipe line visualization (no throttle for visual feedback)
    setSwipeLine({
      id: Date.now(),
      startX: dragStartRef.current.x,
      startY: dragStartRef.current.y,
      endX: event.clientX,
      endY: event.clientY,
    });

    // Throttled MOVE event sending
    const rect = videoRef.current?.getBoundingClientRect();
    if (!rect || !videoRef.current || !deviceResolution) return;

    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    const deviceCoords = getDeviceCoordinates(clickX, clickY, videoRef.current);
    if (!deviceCoords) return;

    // Scale to actual device resolution
    const videoWidth = videoRef.current.videoWidth;
    const videoHeight = videoRef.current.videoHeight;
    const scaleX = deviceResolution.width / videoWidth;
    const scaleY = deviceResolution.height / videoHeight;

    const actualDeviceX = Math.round(deviceCoords.x * scaleX);
    const actualDeviceY = Math.round(deviceCoords.y * scaleY);

    // Check if enough time has passed since last MOVE event
    const now = Date.now();
    if (now - lastMoveTimeRef.current >= MOTION_THROTTLE_MS) {
      // Send immediately
      lastMoveTimeRef.current = now;
      sendTouchMove(actualDeviceX, actualDeviceY, deviceId).catch(error => {
        console.error('[Touch] MOVE failed:', error);
      });
    } else {
      // Store pending move and schedule throttled send
      pendingMoveRef.current = { x: actualDeviceX, y: actualDeviceY };

      if (moveThrottleTimerRef.current) {
        clearTimeout(moveThrottleTimerRef.current);
      }

      moveThrottleTimerRef.current = setTimeout(
        () => {
          if (pendingMoveRef.current) {
            const { x, y } = pendingMoveRef.current;
            lastMoveTimeRef.current = Date.now();
            sendTouchMove(x, y, deviceId).catch(error => {
              console.error('[Touch] MOVE (throttled) failed:', error);
            });
            pendingMoveRef.current = null;
          }
        },
        MOTION_THROTTLE_MS - (now - lastMoveTimeRef.current)
      );
    }
  };

  /**
   * Handle mouse up event for drag end
   */
  const handleMouseUp = async (event: React.MouseEvent<HTMLVideoElement>) => {
    if (!isDraggingRef.current || !dragStartRef.current) return;

    const deltaX = event.clientX - dragStartRef.current.x;
    const deltaY = event.clientY - dragStartRef.current.y;
    const deltaTime = Date.now() - dragStartRef.current.time;

    // Clear swipe line
    setSwipeLine(null);
    isDraggingRef.current = false;

    // Clear any pending throttled MOVE events
    if (moveThrottleTimerRef.current) {
      clearTimeout(moveThrottleTimerRef.current);
      moveThrottleTimerRef.current = null;
    }
    pendingMoveRef.current = null;

    // Check if it's a tap (short movement, short duration)
    const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
    if (distance < 10 && deltaTime < 200) {
      // It's a tap - use existing tap logic
      handleVideoClick(event);
      dragStartRef.current = null;
      return;
    }

    // Send UP event at final position
    const rect = videoRef.current?.getBoundingClientRect();
    if (!rect || !videoRef.current || !deviceResolution) {
      dragStartRef.current = null;
      return;
    }

    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    const deviceCoords = getDeviceCoordinates(clickX, clickY, videoRef.current);
    if (!deviceCoords) {
      dragStartRef.current = null;
      return;
    }

    // Scale to actual device resolution
    const videoWidth = videoRef.current.videoWidth;
    const videoHeight = videoRef.current.videoHeight;
    const scaleX = deviceResolution.width / videoWidth;
    const scaleY = deviceResolution.height / videoHeight;

    const actualDeviceX = Math.round(deviceCoords.x * scaleX);
    const actualDeviceY = Math.round(deviceCoords.y * scaleY);

    try {
      await sendTouchUp(actualDeviceX, actualDeviceY, deviceId);
      console.log(
        `[Touch] UP: (${actualDeviceX}, ${actualDeviceY}) for device ${deviceId}`
      );
      onTapSuccess?.();
    } catch (error) {
      console.error('[Touch] UP failed:', error);
      onTapError?.(String(error));
    }

    dragStartRef.current = null;
  };

  /**
   * Handle wheel event for vertical scrolling with debouncing
   */
  const handleWheel = async (event: React.WheelEvent<HTMLVideoElement>) => {
    if (!enableControl || !videoRef.current || status !== 'connected') return;

    // Prevent default scroll behavior
    // event.preventDefault();

    const now = Date.now();
    const currentDelta = event.deltaY;

    // Initialize or accumulate scroll data
    if (!accumulatedScrollRef.current) {
      accumulatedScrollRef.current = {
        deltaY: 0,
        lastTime: now,
        mouseX: event.clientX,
        mouseY: event.clientY,
      };
    }

    // Accumulate scroll delta and track average mouse position
    accumulatedScrollRef.current.deltaY += currentDelta;
    accumulatedScrollRef.current.lastTime = now;
    // Update mouse position as weighted average to smooth movement
    const currentWeight = 0.3; // Weight for new mouse position
    accumulatedScrollRef.current.mouseX = Math.round(
      accumulatedScrollRef.current.mouseX * (1 - currentWeight) +
        event.clientX * currentWeight
    );
    accumulatedScrollRef.current.mouseY = Math.round(
      accumulatedScrollRef.current.mouseY * (1 - currentWeight) +
        event.clientY * currentWeight
    );

    // Clear existing timeout
    if (wheelTimeoutRef.current) {
      clearTimeout(wheelTimeoutRef.current);
    }

    // Set new timeout to execute scroll after 150ms of inactivity
    wheelTimeoutRef.current = setTimeout(async () => {
      if (!accumulatedScrollRef.current || !videoRef.current) return;

      const totalDelta = accumulatedScrollRef.current;
      accumulatedScrollRef.current = null; // Reset accumulation

      // Validate totalDelta has required properties
      if (totalDelta.mouseX === undefined || totalDelta.mouseY === undefined)
        return;

      // Get accumulated mouse position
      const rect = videoRef.current.getBoundingClientRect();
      const mouseX = totalDelta.mouseX;
      const mouseY = totalDelta.mouseY;

      // Calculate scroll distance from accumulated delta
      const scrollDistance = Math.abs(totalDelta.deltaY);
      const swipeDuration = Math.min(Math.max(300, scrollDistance), 800); // Duration based on distance

      // Convert mouse position to device coordinates
      const mouseDeviceCoords = getDeviceCoordinates(
        mouseX - rect.left,
        mouseY - rect.top,
        videoRef.current
      );

      if (!mouseDeviceCoords || !deviceResolution) {
        console.warn(
          '[ScrcpyPlayer] Cannot execute scroll: coordinate transformation failed'
        );
        return;
      }

      // Scale from video stream resolution to device actual resolution
      const videoWidth = videoRef.current.videoWidth;
      const videoHeight = videoRef.current.videoHeight;
      const scaleX = deviceResolution.width / videoWidth;
      const scaleY = deviceResolution.height / videoHeight;

      const actualCenterX = Math.round(mouseDeviceCoords.x * scaleX);
      const actualCenterY = Math.round(mouseDeviceCoords.y * scaleY);

      // Calculate swipe start and end points (inverted: scroll down = swipe up)
      let startY, endY;
      if (totalDelta.deltaY > 0) {
        // Scroll down - swipe up (from mouse position upward)
        startY = actualCenterY;
        endY = actualCenterY - scrollDistance;
      } else {
        // Scroll up - swipe down (from mouse position downward)
        startY = actualCenterY;
        endY = actualCenterY + scrollDistance;
      }

      // Show scroll indicator aligned with actual swipe trajectory
      // Calculate visual distance using device height to display height ratio (1:1 mapping)
      const deviceScrollDistance = Math.abs(endY - startY);
      const visualDistance = Math.max(
        (deviceScrollDistance / deviceResolution.height) * rect.height, // Direct 1:1 mapping
        20
      );

      // Animation duration proportional to actual swipe duration
      const animationDuration = Math.min(
        Math.max(swipeDuration * 0.8, 200),
        800
      );

      // Create moving ball indicator from mouse position
      const scrollIndicator = document.createElement('div');
      scrollIndicator.style.cssText = `
        position: fixed;
        left: ${mouseX}px;
        top: ${mouseY}px;
        width: 20px;
        height: 20px;
        pointer-events: none;
        z-index: 50;
        transform: translateX(-50%) translateY(-50%);
        background: radial-gradient(circle,
          rgba(59, 130, 246, 0.8) 0%,
          rgba(59, 130, 246, 0.4) 30%,
          rgba(59, 130, 246, 0.2) 60%,
          rgba(59, 130, 246, 0) 100%);
        border-radius: 50%;
        box-shadow: 0 0 10px rgba(59, 130, 246, 0.6);
      `;

      // Create moving ball animation from mouse position
      const startTime = Date.now();
      const moveInterval = setInterval(() => {
        const elapsed = Date.now() - startTime;
        const progressRatio = Math.min(elapsed / animationDuration, 1);

        const ballTop =
          totalDelta.deltaY > 0
            ? mouseY - visualDistance * progressRatio
            : mouseY + visualDistance * progressRatio;

        scrollIndicator.style.top = ballTop + 'px';

        if (progressRatio >= 1) {
          clearInterval(moveInterval);
        }
      }, 16); // 60fps

      document.body.appendChild(scrollIndicator);

      // Remove scroll indicator after animation
      setTimeout(() => {
        if (scrollIndicator.parentNode) {
          scrollIndicator.parentNode.removeChild(scrollIndicator);
        }
        clearInterval(moveInterval);
      }, animationDuration);

      try {
        const result = await sendSwipe(
          actualCenterX,
          startY,
          actualCenterX,
          endY,
          swipeDuration,
          deviceId
        );

        if (result.success) {
          onSwipeSuccess?.();
        } else {
          onSwipeError?.(result.error || 'Scroll failed');
        }
      } catch (error) {
        onSwipeError?.(String(error));
      }
    }, WHEEL_DELAY_MS);

    return;
  };

  /**
   * Handle video click event
   */
  const handleVideoClick = async (
    event: React.MouseEvent<HTMLVideoElement>
  ) => {
    // Guard: Feature disabled
    if (!enableControl) return;

    // Guard: Video not ready
    if (!videoRef.current || status !== 'connected') {
      return;
    }

    // Guard: Video dimensions not available
    if (
      videoRef.current.videoWidth === 0 ||
      videoRef.current.videoHeight === 0
    ) {
      return;
    }

    // Guard: Device resolution not available
    if (!deviceResolution) {
      return;
    }

    // Get click position relative to video element
    const rect = videoRef.current.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    // Transform to device coordinates
    const deviceCoords = getDeviceCoordinates(clickX, clickY, videoRef.current);
    if (!deviceCoords) {
      return;
    }

    // Scale coordinates from video stream resolution to device actual resolution
    const videoWidth = videoRef.current.videoWidth;
    const videoHeight = videoRef.current.videoHeight;
    const scaleX = deviceResolution.width / videoWidth;
    const scaleY = deviceResolution.height / videoHeight;

    const actualDeviceX = Math.round(deviceCoords.x * scaleX);
    const actualDeviceY = Math.round(deviceCoords.y * scaleY);

    // Add ripple effect (use viewport coordinates for fixed positioning)
    const rippleId = Date.now();
    setRipples(prev => [
      ...prev,
      { id: rippleId, x: event.clientX, y: event.clientY },
    ]);

    // Remove ripple after animation (500ms)
    setTimeout(() => {
      setRipples(prev => prev.filter(r => r.id !== rippleId));
    }, 500);

    // Send tap command with actual device coordinates
    try {
      const result = await sendTap(actualDeviceX, actualDeviceY, deviceId);
      if (result.success) {
        onTapSuccess?.();
      } else {
        onTapError?.(result.error || 'Unknown error');
      }
    } catch (error) {
      onTapError?.(String(error));
    }
  };

  // Update refs when props change (without triggering useEffect)
  useEffect(() => {
    onFallbackRef.current = onFallback;
    fallbackTimeoutRef.current = fallbackTimeout;
    onStreamReadyRef.current = onStreamReady;
  }, [onFallback, fallbackTimeout, onStreamReady]);

  // Fetch device actual resolution on mount
  useEffect(() => {
    const fetchDeviceResolution = async () => {
      try {
        const screenshot = await getScreenshot(deviceId);
        if (screenshot.success) {
          setDeviceResolution({
            width: screenshot.width,
            height: screenshot.height,
          });
          console.log(
            `[ScrcpyPlayer] Device actual resolution: ${screenshot.width}x${screenshot.height} for device ${deviceId}`
          );
        }
      } catch (error) {
        console.error(
          '[ScrcpyPlayer] Failed to fetch device resolution:',
          error
        );
      }
    };

    fetchDeviceResolution();
  }, [deviceId]);

  useEffect(() => {
    // Update deviceId ref to always have the latest value
    deviceIdRef.current = deviceId;

    let reconnectTimeout: NodeJS.Timeout | null = null;
    let connectFn: (() => void) | null = null; // Reference to connect function

    const connect = async () => {
      if (!videoRef.current) return;

      console.log('[ScrcpyPlayer] connect() called');
      lastConnectTimeRef.current = Date.now(); // Record connect time
      setStatus('connecting');
      setErrorMessage(null);

      // CRITICAL: Close existing WebSocket before creating new one
      // This prevents duplicate connections
      if (wsRef.current) {
        console.log('[ScrcpyPlayer] Closing existing WebSocket');
        try {
          // Remove event handlers to prevent onclose from triggering reconnect
          wsRef.current.onclose = null;
          wsRef.current.onerror = null;
          wsRef.current.onmessage = null;
          wsRef.current.close();
        } catch (error) {
          console.error('[ScrcpyPlayer] Error closing old WebSocket:', error);
        }
        wsRef.current = null;
      }

      // CRITICAL: Destroy old jMuxer instance before creating new one
      // This prevents multiple jMuxer instances fighting over the same video element
      if (jmuxerRef.current) {
        console.log('[ScrcpyPlayer] Destroying old jMuxer instance');
        try {
          jmuxerRef.current.destroy();
        } catch (error) {
          console.error('[ScrcpyPlayer] Error destroying old jMuxer:', error);
        }
        jmuxerRef.current = null;
      }

      // NOTE: Don't manually reset video.src - let jMuxer manage it
      // Manually resetting causes MEDIA_ERR_SRC_NOT_SUPPORTED errors

      // ✅ CRITICAL: Wait for browser to cleanup MediaSource resources
      // Creating new jMuxer immediately can cause resource conflicts
      await new Promise(resolve => setTimeout(resolve, 300));

      try {
        // Initialize fresh jMuxer with LOW LATENCY settings
        console.log(
          '[ScrcpyPlayer] Creating new jMuxer instance (after cleanup delay)'
        );
        jmuxerRef.current = new jMuxer({
          node: videoRef.current,
          mode: 'video',
          flushingTime: 0, // ✅ Try 0 again since backend data is now correct
          fps: 30,
          debug: false,
          clearBuffer: true, // ✅ Clear buffer on errors to prevent buildup

          // ✅ Enhanced error handling with reset-first strategy
          onError: (error: { name: string; error: string }) => {
            console.error('[jMuxer] Decoder error:', error);

            // Handle buffer errors with progressive recovery strategy
            if (
              error.name === 'InvalidStateError' &&
              error.error === 'buffer error'
            ) {
              const now = Date.now();
              const timeSinceLastReset = now - lastResetTimeRef.current;

              // Debounce: prevent rapid consecutive resets
              if (timeSinceLastReset < RESET_DEBOUNCE_MS) {
                console.warn(
                  `[jMuxer] Reset debounced (${timeSinceLastReset}ms since last reset)`
                );
                return;
              }

              lastResetTimeRef.current = now;
              resetAttemptsRef.current++;

              console.warn(
                `[jMuxer] ⚠️ Buffer error detected (attempt ${resetAttemptsRef.current}/${MAX_RESET_ATTEMPTS})`
              );

              // Strategy: Try reset() first, only reconnect as last resort
              if (resetAttemptsRef.current <= MAX_RESET_ATTEMPTS) {
                // ✅ OPTIMIZED: Use reset() instead of destroy + reconnect
                if (jmuxerRef.current) {
                  try {
                    console.log('[jMuxer] Attempting lightweight reset()...');
                    jmuxerRef.current.reset();
                    console.log('[jMuxer] ✓ Reset successful');

                    // If reset succeeds, don't reconnect WebSocket
                    // Just continue receiving data on existing connection
                    return;
                  } catch (resetError) {
                    console.error('[jMuxer] Reset failed:', resetError);
                    // Fall through to full reconnect
                  }
                }
              }

              // CRITICAL: After reset, decoder needs fresh SPS+PPS+IDR
              // Close and reconnect WebSocket to get initialization data
              console.log(
                '[jMuxer] Reset successful, reconnecting to get fresh initialization data...'
              );

              lastErrorTimeRef.current = now;
              const errorDeviceId = currentDeviceId;

              if (connectFn) {
                setTimeout(() => {
                  if (deviceIdRef.current === errorDeviceId) {
                    if (connectFn) {
                      connectFn();
                    }
                  } else {
                    console.log(
                      `[jMuxer] Device changed (${errorDeviceId} -> ${deviceIdRef.current}), skip reconnect`
                    );
                  }
                }, 100);
              }
            }
          },

          // ✅ Disabled: jMuxer has a bug treating H.264 slices as separate frames (Issue #44)
          // This causes false "Missing video frames" warnings when frames are sliced (common in complex scenes)
          // See: https://github.com/samirkumardas/jmuxer/issues/44
          onMissingVideoFrames: (frames: unknown) => {
            console.warn('[jMuxer] Missing video frames detected:', frames);
          },
        });

        // Connect WebSocket (with device_id parameter)
        // Use deviceIdRef.current to always get the latest deviceId, even during reconnects
        const currentDeviceId = deviceIdRef.current;
        const wsUrl = `ws://localhost:8000/api/video/stream?device_id=${encodeURIComponent(currentDeviceId)}`;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
          console.log(
            `[ScrcpyPlayer] WebSocket connected for device ${currentDeviceId}`
          );
          setStatus('connected');

          // ✅ Reset error recovery counters on successful connection
          resetAttemptsRef.current = 0;
          lastResetTimeRef.current = 0;

          // Notify parent component that video stream is ready
          if (onStreamReadyRef.current) {
            onStreamReadyRef.current({
              close: () => {
                ws.close();
              },
            });
          }

          // Start fallback timer
          fallbackTimerRef.current = setTimeout(() => {
            if (!hasReceivedDataRef.current) {
              console.log(
                '[ScrcpyPlayer] No data received within timeout, triggering fallback'
              );
              setStatus('error');
              setErrorMessage('Video stream timeout');
              ws.close();
              if (onFallbackRef.current) {
                onFallbackRef.current();
              }
            }
          }, fallbackTimeoutRef.current);
        };

        ws.onmessage = event => {
          if (typeof event.data === 'string') {
            // Error message from server
            try {
              const error = JSON.parse(event.data);
              console.error('[ScrcpyPlayer] Server error:', error);
              setErrorMessage(error.error || 'Unknown error');
              setStatus('error');

              // Trigger fallback on error
              if (onFallbackRef.current && !hasReceivedDataRef.current) {
                onFallbackRef.current();
              }
            } catch {
              console.error(
                '[ScrcpyPlayer] Received non-JSON string:',
                event.data
              );
            }
            return;
          }

          // Log first message (initialization data: SPS+PPS+IDR)
          if (!hasReceivedDataRef.current) {
            const data = new Uint8Array(event.data);
            console.log(
              `[ScrcpyPlayer] ✓ Received initialization data (${data.length} bytes)`
            );

            // Count NAL units in initialization data
            let nalCount = 0;
            for (let i = 0; i < data.length - 3; i++) {
              if (
                data[i] === 0x00 &&
                data[i + 1] === 0x00 &&
                (data[i + 2] === 0x01 ||
                  (data[i + 2] === 0x00 && data[i + 3] === 0x01))
              ) {
                nalCount++;
              }
            }
            console.log(
              `[ScrcpyPlayer] Initialization data contains ${nalCount} NAL units`
            );
          }

          // H.264 video data received successfully
          if (!hasReceivedDataRef.current) {
            hasReceivedDataRef.current = true;
            console.log(
              '[ScrcpyPlayer] First video data received, canceling fallback timer'
            );
            if (fallbackTimerRef.current) {
              clearTimeout(fallbackTimerRef.current);
              fallbackTimerRef.current = null;
            }
          }

          // Feed to jMuxer - each WebSocket message is one complete NAL unit
          // Backend ensures NAL unit boundaries, frontend just needs to pass through
          try {
            if (jmuxerRef.current && event.data.byteLength > 0) {
              const videoData = new Uint8Array(event.data);

              // Validate NAL unit structure (should start with start code)
              const hasStartCode =
                videoData[0] === 0x00 &&
                videoData[1] === 0x00 &&
                (videoData[2] === 0x00 || videoData[2] === 0x01);

              if (!hasStartCode) {
                console.warn(
                  `[ScrcpyPlayer] Invalid NAL unit: missing start code, first bytes = ${Array.from(
                    videoData.slice(0, 8)
                  )
                    .map(b => b.toString(16).padStart(2, '0'))
                    .join(' ')}`
                );
              }

              // Extract NAL type for debugging (skip for first message which is multi-NAL init data)
              if (hasReceivedDataRef.current) {
                const nalHeaderOffset = videoData[2] === 0x01 ? 3 : 4;
                const nalType = videoData[nalHeaderOffset] & 0x1f;

                // Log important NAL units (SPS=7, PPS=8, IDR=5)
                if (nalType === 5 || nalType === 7 || nalType === 8) {
                  const typeNames: Record<number, string> = {
                    5: 'IDR',
                    7: 'SPS',
                    8: 'PPS',
                  };
                  console.log(
                    `[ScrcpyPlayer] Received ${typeNames[nalType]} NAL unit (${videoData.length} bytes)`
                  );
                }
              }

              // Feed complete NAL unit to jMuxer
              jmuxerRef.current.feed({
                video: videoData,
              });

              // Monitor frame rate and detect buffer buildup
              frameCountRef.current++;
              const now = Date.now();
              const elapsed = now - lastStatsTimeRef.current;

              if (elapsed > 5000) {
                // Log stats every 5 seconds
                const fps = (frameCountRef.current / elapsed) * 1000;
                const videoEl = videoRef.current;
                const buffered =
                  videoEl && videoEl.buffered.length > 0
                    ? videoEl.buffered.end(0) - videoEl.currentTime
                    : 0;

                console.log(
                  `[ScrcpyPlayer] Stats: ${fps.toFixed(1)} fps, buffer: ${buffered.toFixed(2)}s`
                );

                // ✅ WARNING: If buffer > 2 seconds, we're falling behind
                if (buffered > 2) {
                  console.warn(
                    `[ScrcpyPlayer] ⚠ High latency detected: ${buffered.toFixed(2)}s buffer`
                  );
                }

                frameCountRef.current = 0;
                lastStatsTimeRef.current = now;
              }
            }
          } catch (error) {
            console.error('[ScrcpyPlayer] Feed error:', error);
          }
        };

        ws.onerror = error => {
          console.error('[ScrcpyPlayer] WebSocket error:', error);
          setErrorMessage('Connection error');
          setStatus('error');
        };

        ws.onclose = () => {
          console.log('[ScrcpyPlayer] WebSocket closed');
          setStatus('disconnected');

          // Notify parent component that video stream is disconnected
          if (onStreamReadyRef.current) {
            onStreamReadyRef.current(null);
          }

          // Auto-reconnect after 3 seconds
          // But only if we're still on the same device
          const closedDeviceId = currentDeviceId; // Capture device ID at close time
          reconnectTimeout = setTimeout(() => {
            // Check if device hasn't changed before reconnecting
            if (deviceIdRef.current === closedDeviceId) {
              console.log('[ScrcpyPlayer] Attempting to reconnect...');
              connect();
            } else {
              console.log(
                `[ScrcpyPlayer] Device changed (${closedDeviceId} -> ${deviceIdRef.current}), skip reconnect`
              );
            }
          }, 3000);
        };
      } catch (error) {
        console.error('[ScrcpyPlayer] Initialization error:', error);
        setErrorMessage('Initialization failed');
        setStatus('error');
      }
    };

    // Make connect function accessible to jMuxer error handler
    connectFn = connect;

    connect();

    // Cleanup
    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }

      if (fallbackTimerRef.current) {
        clearTimeout(fallbackTimerRef.current);
        fallbackTimerRef.current = null;
      }

      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      // Cleanup motion throttle timer
      if (moveThrottleTimerRef.current) {
        clearTimeout(moveThrottleTimerRef.current);
        moveThrottleTimerRef.current = null;
      }

      if (jmuxerRef.current) {
        try {
          jmuxerRef.current.destroy();
        } catch (error) {
          console.error('[ScrcpyPlayer] Cleanup error:', error);
        }
        jmuxerRef.current = null;
      }
    };
  }, [deviceId]);

  return (
    <div
      className={`relative w-full h-full flex items-center justify-center ${className || ''}`}
    >
      {/* Video element */}
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        onError={e => {
          const videoEl = e.currentTarget;
          const error = videoEl.error;
          if (error) {
            console.error('[Video Element] Error occurred:', {
              code: error.code,
              message: error.message,
              MEDIA_ERR_ABORTED: error.code === 1,
              MEDIA_ERR_NETWORK: error.code === 2,
              MEDIA_ERR_DECODE: error.code === 3,
              MEDIA_ERR_SRC_NOT_SUPPORTED: error.code === 4,
            });
          }
        }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={async () => {
          // Cancel drag if mouse leaves video area
          if (isDraggingRef.current && videoRef.current && deviceResolution) {
            // Send UP event to cancel incomplete gesture
            if (dragStartRef.current) {
              const rect = videoRef.current.getBoundingClientRect();
              // Use dragStart as fallback position
              const deviceCoords = getDeviceCoordinates(
                dragStartRef.current.x - rect.left,
                dragStartRef.current.y - rect.top,
                videoRef.current
              );

              if (deviceCoords) {
                const scaleX =
                  deviceResolution.width / videoRef.current.videoWidth;
                const scaleY =
                  deviceResolution.height / videoRef.current.videoHeight;
                const x = Math.round(deviceCoords.x * scaleX);
                const y = Math.round(deviceCoords.y * scaleY);

                try {
                  await sendTouchUp(x, y, deviceId);
                  console.log(
                    `[Touch] UP (mouse leave) for device ${deviceId}`
                  );
                } catch (error) {
                  console.error('[Touch] UP (mouse leave) failed:', error);
                }
              }
            }

            isDraggingRef.current = false;
            setSwipeLine(null);
            dragStartRef.current = null;
          }
        }}
        onWheel={handleWheel}
        className={`max-w-full max-h-full object-contain ${
          enableControl ? 'cursor-pointer' : ''
        }`}
        style={{ backgroundColor: '#000' }}
      />

      {/* Swipe line visualization */}
      {enableControl && swipeLine && (
        <svg className="fixed inset-0 pointer-events-none z-40">
          <line
            x1={swipeLine.startX}
            y1={swipeLine.startY}
            x2={swipeLine.endX}
            y2={swipeLine.endY}
            stroke="rgba(59, 130, 246, 0.8)"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <circle
            cx={swipeLine.startX}
            cy={swipeLine.startY}
            r="6"
            fill="rgba(59, 130, 246, 0.8)"
          />
          <circle
            cx={swipeLine.endX}
            cy={swipeLine.endY}
            r="6"
            fill="rgba(239, 68, 68, 0.8)"
          />
        </svg>
      )}

      {/* Ripple effects overlay */}
      {enableControl &&
        ripples.map(ripple => (
          <div
            key={ripple.id}
            className="fixed pointer-events-none z-50"
            style={{
              left: ripple.x,
              top: ripple.y,
            }}
          >
            <div className="ripple-circle" />
          </div>
        ))}

      {/* Status overlay */}
      {status !== 'connected' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="text-center text-white">
            {status === 'connecting' && (
              <>
                <div className="w-8 h-8 border-4 border-white border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                <p>正在连接...</p>
              </>
            )}
            {status === 'disconnected' && (
              <>
                <div className="w-8 h-8 border-4 border-yellow-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                <p>连接断开，正在重连...</p>
              </>
            )}
            {status === 'error' && (
              <>
                <div className="text-red-500 text-xl mb-2">✗</div>
                <p className="text-red-400">连接失败</p>
                {errorMessage && (
                  <p className="text-sm text-gray-400 mt-1">{errorMessage}</p>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
