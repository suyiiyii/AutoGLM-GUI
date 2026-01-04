import type { MouseEvent, WheelEvent } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Socket } from 'socket.io-client';
import { io } from 'socket.io-client';
import { ScrcpyVideoCodecId } from '@yume-chan/scrcpy';
import {
  BitmapVideoFrameRenderer,
  WebCodecsVideoDecoder,
  WebGLVideoFrameRenderer,
} from '@yume-chan/scrcpy-decoder-webcodecs';
import {
  getScreenshot,
  sendSwipe,
  sendTouchDown,
  sendTouchMove,
  sendTouchUp,
} from '../api';

const MOTION_THROTTLE_MS = 50;
const WHEEL_DELAY_MS = 300;

interface ScrcpyPlayerProps {
  deviceId: string;
  className?: string;
  onFallback?: () => void;
  fallbackTimeout?: number;
  enableControl?: boolean;
  onTapSuccess?: () => void;
  onTapError?: (error: string) => void;
  onSwipeSuccess?: () => void;
  onSwipeError?: (error: string) => void;
  onStreamReady?: (stream: { close: () => void } | null) => void;
}

interface VideoMetadata {
  deviceName?: string;
  width?: number;
  height?: number;
  codec?: number;
}

interface VideoPacket {
  type: 'configuration' | 'data';
  data: ArrayBuffer | Uint8Array;
  keyframe?: boolean;
  pts?: number;
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
  const socketRef = useRef<Socket | null>(null);
  const decoderRef = useRef<WebCodecsVideoDecoder | null>(null);
  const videoContainerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const fallbackTimerRef = useRef<number | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const connectDeviceRef = useRef<(() => void) | null>(null);
  const hasReceivedDataRef = useRef(false);
  const suppressReconnectRef = useRef(false);
  const onFallbackRef = useRef(onFallback);
  const fallbackTimeoutRef = useRef(fallbackTimeout);
  const onStreamReadyRef = useRef(onStreamReady);

  const [status, setStatus] = useState<
    'connecting' | 'connected' | 'error' | 'disconnected'
  >('connecting');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [screenInfo, setScreenInfo] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [deviceResolution, setDeviceResolution] = useState<{
    width: number;
    height: number;
  } | null>(null);

  const isDraggingRef = useRef(false);
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);
  const movedRef = useRef(false);
  const lastMoveTimeRef = useRef<number>(0);
  const pendingMoveRef = useRef<{ x: number; y: number } | null>(null);
  const moveThrottleTimerRef = useRef<number | null>(null);
  const wheelTimeoutRef = useRef<number | null>(null);
  const accumulatedScrollRef = useRef<{ deltaY: number } | null>(null);

  useEffect(() => {
    onFallbackRef.current = onFallback;
    fallbackTimeoutRef.current = fallbackTimeout;
    onStreamReadyRef.current = onStreamReady;
  }, [onFallback, fallbackTimeout, onStreamReady]);

  useEffect(() => {
    const fetchDeviceResolution = async () => {
      try {
        const screenshot = await getScreenshot(deviceId);
        if (screenshot.success) {
          setDeviceResolution({
            width: screenshot.width,
            height: screenshot.height,
          });
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

  const updateCanvasSize = useCallback(() => {
    const canvas = canvasRef.current;
    const container = videoContainerRef.current;
    if (!canvas || !container || !screenInfo) return;

    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;
    const { width: originalWidth, height: originalHeight } = screenInfo;

    const aspectRatio = originalWidth / originalHeight;
    let targetWidth = containerWidth;
    let targetHeight = containerWidth / aspectRatio;

    if (targetHeight > containerHeight) {
      targetHeight = containerHeight;
      targetWidth = containerHeight * aspectRatio;
    }

    canvas.width = originalWidth;
    canvas.height = originalHeight;
    canvas.style.width = `${targetWidth}px`;
    canvas.style.height = `${targetHeight}px`;
  }, [screenInfo]);

  useEffect(() => {
    const handleResize = () => updateCanvasSize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [updateCanvasSize]);

  useEffect(() => {
    updateCanvasSize();
  }, [screenInfo, updateCanvasSize]);

  const createVideoFrameRenderer = useCallback(async () => {
    if (WebGLVideoFrameRenderer.isSupported) {
      const renderer = new WebGLVideoFrameRenderer();
      return {
        renderer,
        element: renderer.canvas as HTMLCanvasElement,
      };
    }

    const renderer = new BitmapVideoFrameRenderer();
    return {
      renderer,
      element: renderer.canvas as HTMLCanvasElement,
    };
  }, []);

  const createDecoder = useCallback(
    async (codecId: ScrcpyVideoCodecId) => {
      if (!WebCodecsVideoDecoder.isSupported) {
        throw new Error(
          'Current browser does not support WebCodecs API. Please use the latest Chrome/Edge.'
        );
      }

      const { renderer, element } = await createVideoFrameRenderer();
      canvasRef.current = element;

      // Only append if not already appended (check if canvas is in DOM)
      if (videoContainerRef.current && !element.parentElement) {
        videoContainerRef.current.appendChild(element);
      }

      return new WebCodecsVideoDecoder({
        codec: codecId,
        renderer,
      });
    },
    [createVideoFrameRenderer]
  );

  const markDataReceived = useCallback(() => {
    if (hasReceivedDataRef.current) return;
    hasReceivedDataRef.current = true;
    if (fallbackTimerRef.current) {
      clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
  }, []);

  const setupVideoStream = useCallback(
    (_metadata: VideoMetadata) => {
      let configurationPacketSent = false;
      let pendingDataPackets: VideoPacket[] = [];

      const transformStream = new TransformStream<VideoPacket, VideoPacket>({
        transform(packet, controller) {
          if (packet.type === 'configuration') {
            controller.enqueue(packet);
            configurationPacketSent = true;

            if (pendingDataPackets.length > 0) {
              pendingDataPackets.forEach(p => controller.enqueue(p));
              pendingDataPackets = [];
            }
            return;
          }

          if (packet.type === 'data' && !configurationPacketSent) {
            pendingDataPackets.push(packet);
            return;
          }

          controller.enqueue(packet);
        },
      });

      const videoStream = new ReadableStream<VideoPacket>({
        start(controller) {
          let streamClosed = false;

          const videoDataHandler = (data: VideoPacket) => {
            if (streamClosed) return;
            try {
              markDataReceived();
              const payload = {
                ...data,
                data:
                  data.data instanceof Uint8Array
                    ? data.data
                    : new Uint8Array(data.data),
              };
              controller.enqueue(payload);
            } catch (error) {
              console.error('[ScrcpyPlayer] Video enqueue error:', error);
              streamClosed = true;
              cleanup();
            }
          };

          const errorHandler = (error: { message?: string }) => {
            if (streamClosed) return;
            controller.error(new Error(error?.message || 'Socket error'));
            streamClosed = true;
            cleanup();
          };

          const disconnectHandler = () => {
            if (streamClosed) return;
            controller.close();
            streamClosed = true;
            cleanup();
          };

          const cleanup = () => {
            socketRef.current?.off('video-data', videoDataHandler);
            socketRef.current?.off('error', errorHandler);
            socketRef.current?.off('disconnect', disconnectHandler);
          };

          socketRef.current?.on('video-data', videoDataHandler);
          socketRef.current?.on('error', errorHandler);
          socketRef.current?.on('disconnect', disconnectHandler);

          return () => {
            streamClosed = true;
            cleanup();
          };
        },
      });

      return videoStream.pipeThrough(transformStream);
    },
    [markDataReceived]
  );

  const disconnectDevice = useCallback((suppressReconnect = false) => {
    if (suppressReconnect) {
      suppressReconnectRef.current = true;
    }
    if (decoderRef.current) {
      try {
        decoderRef.current.dispose();
      } catch (error) {
        console.error('[ScrcpyPlayer] Failed to dispose decoder:', error);
      }
      decoderRef.current = null;
    }

    // Just clear the reference, let React handle DOM cleanup
    canvasRef.current = null;

    if (socketRef.current) {
      socketRef.current.disconnect();
      socketRef.current = null;
    }

    onStreamReadyRef.current?.(null);

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    if (fallbackTimerRef.current) {
      clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }

    setStatus('disconnected');
    setScreenInfo(null);
    setErrorMessage(null);
  }, []);

  const connectDevice = useCallback(() => {
    disconnectDevice(true);
    hasReceivedDataRef.current = false;
    setStatus('connecting');
    setErrorMessage(null);

    const socket = io({
      path: '/socket.io',
      transports: ['websocket'],
      timeout: 10000,
    });
    socketRef.current = socket;

    socket.on('connect', () => {
      socket.emit('connect-device', {
        device_id: deviceId,
        maxSize: 1280,
        bitRate: 4_000_000,
      });

      fallbackTimerRef.current = setTimeout(() => {
        if (!hasReceivedDataRef.current) {
          setStatus('error');
          setErrorMessage('Video stream timeout');
          suppressReconnectRef.current = true;
          socket.close();
          onFallbackRef.current?.();
        }
      }, fallbackTimeoutRef.current);
    });

    socket.on('video-metadata', async (metadata: VideoMetadata) => {
      try {
        if (decoderRef.current) {
          decoderRef.current.dispose();
          decoderRef.current = null;
        }

        const codecId = metadata?.codec
          ? (metadata.codec as ScrcpyVideoCodecId)
          : ScrcpyVideoCodecId.H264;

        decoderRef.current = await createDecoder(codecId);
        decoderRef.current.sizeChanged(({ width, height }) => {
          setScreenInfo({ width, height });
        });

        const videoStream = setupVideoStream(metadata);
        videoStream
          .pipeTo(decoderRef.current.writable as WritableStream<VideoPacket>)
          .catch((error: Error) => {
            console.error('[ScrcpyPlayer] Video stream error:', error);
          });

        setStatus('connected');
        onStreamReadyRef.current?.({ close: () => socket.close() });
      } catch (error) {
        console.error('[ScrcpyPlayer] Decoder initialization failed:', error);
        setStatus('error');
        setErrorMessage('Decoder initialization failed');
        suppressReconnectRef.current = true;
        socket.close();
        onFallbackRef.current?.();
      }
    });

    socket.on('error', (error: { message?: string }) => {
      console.error('[ScrcpyPlayer] Socket error:', error);
      setStatus('error');
      setErrorMessage(error?.message || 'Socket error');

      if (suppressReconnectRef.current) {
        return;
      }

      onStreamReadyRef.current?.(null);

      if (!reconnectTimerRef.current) {
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          connectDeviceRef.current?.();
        }, 3000);
      }
    });

    socket.on('disconnect', () => {
      if (suppressReconnectRef.current) {
        suppressReconnectRef.current = false;
        return;
      }

      setStatus('disconnected');
      onStreamReadyRef.current?.(null);

      if (!reconnectTimerRef.current) {
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          connectDeviceRef.current?.();
        }, 3000);
      }
    });
  }, [deviceId, disconnectDevice, createDecoder, setupVideoStream]);

  useEffect(() => {
    connectDeviceRef.current = connectDevice;
  }, [connectDevice]);

  useEffect(() => {
    // Use queueMicrotask to avoid synchronous setState within effect
    queueMicrotask(() => {
      connectDevice();
    });

    return () => {
      if (moveThrottleTimerRef.current) {
        clearTimeout(moveThrottleTimerRef.current);
        moveThrottleTimerRef.current = null;
      }

      if (wheelTimeoutRef.current) {
        clearTimeout(wheelTimeoutRef.current);
        wheelTimeoutRef.current = null;
      }

      disconnectDevice(true);
    };
  }, [connectDevice, disconnectDevice]);

  const getStreamDimensions = () => {
    if (screenInfo) {
      return { width: screenInfo.width, height: screenInfo.height };
    }
    const canvas = canvasRef.current;
    if (!canvas) return null;
    return { width: canvas.width, height: canvas.height };
  };

  const mapToDeviceCoordinates = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    const streamDimensions = getStreamDimensions();
    if (!canvas || !streamDimensions) return null;

    const rect = canvas.getBoundingClientRect();
    if (
      clientX < rect.left ||
      clientX > rect.right ||
      clientY < rect.top ||
      clientY > rect.bottom
    ) {
      return null;
    }

    const relativeX = clientX - rect.left;
    const relativeY = clientY - rect.top;

    const streamX = Math.round(
      (relativeX / rect.width) * streamDimensions.width
    );
    const streamY = Math.round(
      (relativeY / rect.height) * streamDimensions.height
    );

    const scaleX = deviceResolution
      ? deviceResolution.width / streamDimensions.width
      : 1;
    const scaleY = deviceResolution
      ? deviceResolution.height / streamDimensions.height
      : 1;

    return {
      x: Math.round(streamX * scaleX),
      y: Math.round(streamY * scaleY),
    };
  };

  const handleMouseDown = async (event: MouseEvent<HTMLDivElement>) => {
    if (!enableControl || status !== 'connected') return;

    const coords = mapToDeviceCoordinates(event.clientX, event.clientY);
    if (!coords) return;

    isDraggingRef.current = true;
    movedRef.current = false;
    dragStartRef.current = { x: event.clientX, y: event.clientY };

    try {
      await sendTouchDown(coords.x, coords.y, deviceId);
    } catch (error) {
      console.error('[ScrcpyPlayer] Touch down failed:', error);
    }
  };

  const handleMouseMove = (event: MouseEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current || status !== 'connected') return;

    const now = Date.now();
    const coords = mapToDeviceCoordinates(event.clientX, event.clientY);
    if (!coords) return;

    if (dragStartRef.current) {
      const dx = event.clientX - dragStartRef.current.x;
      const dy = event.clientY - dragStartRef.current.y;
      if (Math.hypot(dx, dy) > 4) {
        movedRef.current = true;
      }
    }

    pendingMoveRef.current = coords;
    if (now - lastMoveTimeRef.current < MOTION_THROTTLE_MS) {
      if (!moveThrottleTimerRef.current) {
        moveThrottleTimerRef.current = setTimeout(() => {
          moveThrottleTimerRef.current = null;
          if (pendingMoveRef.current) {
            sendTouchMove(
              pendingMoveRef.current.x,
              pendingMoveRef.current.y,
              deviceId
            ).catch(error => {
              console.error('[ScrcpyPlayer] Touch move failed:', error);
            });
            pendingMoveRef.current = null;
            lastMoveTimeRef.current = Date.now();
          }
        }, MOTION_THROTTLE_MS);
      }
      return;
    }

    lastMoveTimeRef.current = now;
    sendTouchMove(coords.x, coords.y, deviceId).catch(error => {
      console.error('[ScrcpyPlayer] Touch move failed:', error);
    });
  };

  const handleMouseUp = async (event: MouseEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current || status !== 'connected') return;

    const coords = mapToDeviceCoordinates(event.clientX, event.clientY);
    isDraggingRef.current = false;
    dragStartRef.current = null;

    if (!coords) return;

    try {
      await sendTouchUp(coords.x, coords.y, deviceId);
      if (!movedRef.current) {
        onTapSuccess?.();
      } else {
        onSwipeSuccess?.();
      }
    } catch (error) {
      const message = String(error);
      if (!movedRef.current) {
        onTapError?.(message);
      } else {
        onSwipeError?.(message);
      }
    }
  };

  const handleMouseLeave = async (event: MouseEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current || status !== 'connected') return;

    const coords = mapToDeviceCoordinates(event.clientX, event.clientY);
    isDraggingRef.current = false;
    dragStartRef.current = null;

    if (!coords) return;

    try {
      await sendTouchUp(coords.x, coords.y, deviceId);
    } catch (error) {
      console.error('[ScrcpyPlayer] Touch cancel failed:', error);
    }
  };

  const handleWheel = (event: WheelEvent<HTMLDivElement>) => {
    if (!enableControl || status !== 'connected') return;

    event.preventDefault();
    const deltaY = event.deltaY;

    if (!accumulatedScrollRef.current) {
      accumulatedScrollRef.current = { deltaY: 0 };
    }
    accumulatedScrollRef.current.deltaY += deltaY;

    if (wheelTimeoutRef.current) {
      clearTimeout(wheelTimeoutRef.current);
    }

    wheelTimeoutRef.current = setTimeout(async () => {
      const current = accumulatedScrollRef.current;
      accumulatedScrollRef.current = null;
      if (!current) return;

      const canvas = canvasRef.current;
      const streamDimensions = getStreamDimensions();
      if (!canvas || !streamDimensions) return;

      const rect = canvas.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      const startCoords = mapToDeviceCoordinates(centerX, centerY);
      if (!startCoords) return;

      const delta = Math.max(Math.min(current.deltaY, 600), -600);
      const endClientY = centerY + delta;
      const endCoords = mapToDeviceCoordinates(centerX, endClientY);
      if (!endCoords) return;

      try {
        const result = await sendSwipe(
          startCoords.x,
          startCoords.y,
          endCoords.x,
          endCoords.y,
          300,
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
  };

  return (
    <div
      className={`relative w-full h-full flex items-center justify-center ${className || ''}`}
    >
      <div
        ref={videoContainerRef}
        className="relative w-full h-full flex items-center justify-center bg-slate-50 dark:bg-slate-900"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onWheel={handleWheel}
      >
        {status !== 'connected' && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400">
            {status === 'connecting' && 'Connecting...'}
            {status === 'error' && (errorMessage || 'Connection error')}
            {status === 'disconnected' && 'Disconnected'}
          </div>
        )}
      </div>
    </div>
  );
}
