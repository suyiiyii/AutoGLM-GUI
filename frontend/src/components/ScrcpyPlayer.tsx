import { useEffect, useRef, useState } from 'react';
import jMuxer from 'jmuxer';

interface ScrcpyPlayerProps {
  className?: string;
  onFallback?: () => void; // Callback when fallback to screenshot is needed
  fallbackTimeout?: number; // Timeout in ms before fallback (default 5000)
}

export function ScrcpyPlayer({ className, onFallback, fallbackTimeout = 5000 }: ScrcpyPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const jmuxerRef = useRef<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<'connecting' | 'connected' | 'error' | 'disconnected'>('connecting');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fallbackTimerRef = useRef<NodeJS.Timeout | null>(null);
  const hasReceivedDataRef = useRef(false);

  // Latency monitoring
  const frameCountRef = useRef(0);
  const lastStatsTimeRef = useRef(Date.now());

  // Error recovery (debounce reconnects)
  const lastErrorTimeRef = useRef(0);
  const lastConnectTimeRef = useRef(0);

  // Use ref to store latest callback to avoid useEffect re-running
  const onFallbackRef = useRef(onFallback);
  const fallbackTimeoutRef = useRef(fallbackTimeout);

  // Update refs when props change (without triggering useEffect)
  useEffect(() => {
    onFallbackRef.current = onFallback;
    fallbackTimeoutRef.current = fallbackTimeout;
  }, [onFallback, fallbackTimeout]);

  useEffect(() => {
    let reconnectTimeout: NodeJS.Timeout | null = null;
    let connectFn: (() => void) | null = null;  // Reference to connect function

    const connect = async () => {
      if (!videoRef.current) return;

      console.log('[ScrcpyPlayer] connect() called');
      lastConnectTimeRef.current = Date.now();  // Record connect time
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

      // Reset video element to clean state
      if (videoRef.current) {
        videoRef.current.src = '';
        videoRef.current.load();
      }

      // ✅ CRITICAL: Wait for browser to cleanup MediaSource resources
      // Creating new jMuxer immediately can cause resource conflicts
      await new Promise(resolve => setTimeout(resolve, 300));

      try {
        // Initialize fresh jMuxer with LOW LATENCY settings
        console.log('[ScrcpyPlayer] Creating new jMuxer instance (after cleanup delay)');
        jmuxerRef.current = new jMuxer({
          node: videoRef.current,
          mode: 'video',
          flushingTime: 0,  // ✅ 0 = lowest latency (no buffering)
          fps: 30,
          debug: false,
          clearBuffer: true,  // ✅ Clear buffer on errors to prevent buildup
          onError: (error: any) => {
            console.error('[jMuxer] Decoder error:', error);

            // ✅ On buffer error, immediately reconnect
            if (error.name === 'InvalidStateError' && error.error === 'buffer error') {
              const now = Date.now();
              const timeSinceLastError = now - lastErrorTimeRef.current;
              const timeSinceConnect = now - lastConnectTimeRef.current;

              // Smart debounce logic:
              // - If error happens soon after connect (< 1s), allow quick retry
              //   (means connection itself failed, not buffer overflow)
              // - Otherwise, require 2s between reconnects
              const shouldReconnect = timeSinceConnect < 1000
                ? timeSinceLastError > 500  // Quick retry for new connection failures
                : timeSinceLastError > 2000;  // Normal debounce for buffer overflows

              if (shouldReconnect) {
                lastErrorTimeRef.current = now;
                console.warn('[jMuxer] ⚠️ Buffer error detected, reconnecting...');

                // Immediate reconnect
                if (connectFn) {
                  setTimeout(() => {
                    connectFn!();
                  }, 100);
                }
              } else {
                console.warn(`[jMuxer] Reconnect skipped (debounced: ${timeSinceLastError}ms since last error)`);
              }
            }
          },
        });

        // Connect WebSocket
        const ws = new WebSocket('ws://localhost:8000/api/video/stream');
        wsRef.current = ws;
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
          console.log('[ScrcpyPlayer] WebSocket connected');
          setStatus('connected');

          // Start fallback timer
          fallbackTimerRef.current = setTimeout(() => {
            if (!hasReceivedDataRef.current) {
              console.log('[ScrcpyPlayer] No data received within timeout, triggering fallback');
              setStatus('error');
              setErrorMessage('Video stream timeout');
              ws.close();
              if (onFallbackRef.current) {
                onFallbackRef.current();
              }
            }
          }, fallbackTimeoutRef.current);
        };

        ws.onmessage = (event) => {
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
              console.error('[ScrcpyPlayer] Received non-JSON string:', event.data);
            }
            return;
          }

          // H.264 video data received successfully
          if (!hasReceivedDataRef.current) {
            hasReceivedDataRef.current = true;
            console.log('[ScrcpyPlayer] First video data received, canceling fallback timer');
            if (fallbackTimerRef.current) {
              clearTimeout(fallbackTimerRef.current);
              fallbackTimerRef.current = null;
            }
          }

          // Feed to jMuxer
          try {
            if (jmuxerRef.current && event.data.byteLength > 0) {
              jmuxerRef.current.feed({
                video: new Uint8Array(event.data),
              });

              // Monitor frame rate and detect buffer buildup
              frameCountRef.current++;
              const now = Date.now();
              const elapsed = now - lastStatsTimeRef.current;

              if (elapsed > 5000) {  // Log stats every 5 seconds
                const fps = (frameCountRef.current / elapsed) * 1000;
                const videoEl = videoRef.current;
                const buffered = videoEl && videoEl.buffered.length > 0
                  ? videoEl.buffered.end(0) - videoEl.currentTime
                  : 0;

                console.log(`[ScrcpyPlayer] Stats: ${fps.toFixed(1)} fps, buffer: ${buffered.toFixed(2)}s`);

                // ✅ WARNING: If buffer > 2 seconds, we're falling behind
                if (buffered > 2) {
                  console.warn(`[ScrcpyPlayer] ⚠ High latency detected: ${buffered.toFixed(2)}s buffer`);
                }

                frameCountRef.current = 0;
                lastStatsTimeRef.current = now;
              }
            }
          } catch (error) {
            console.error('[ScrcpyPlayer] Feed error:', error);
          }
        };

        ws.onerror = (error) => {
          console.error('[ScrcpyPlayer] WebSocket error:', error);
          setErrorMessage('Connection error');
          setStatus('error');
        };

        ws.onclose = () => {
          console.log('[ScrcpyPlayer] WebSocket closed');
          setStatus('disconnected');

          // Auto-reconnect after 3 seconds
          reconnectTimeout = setTimeout(() => {
            console.log('[ScrcpyPlayer] Attempting to reconnect...');
            connect();
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

      if (jmuxerRef.current) {
        try {
          jmuxerRef.current.destroy();
        } catch (error) {
          console.error('[ScrcpyPlayer] Cleanup error:', error);
        }
        jmuxerRef.current = null;
      }
    };
  }, []); // Empty deps: only run once on mount

  return (
    <div className={`relative w-full h-full flex items-center justify-center ${className || ''}`}>
      {/* Video element */}
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        className="max-w-full max-h-full object-contain"
        style={{ backgroundColor: '#000' }}
      />

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
