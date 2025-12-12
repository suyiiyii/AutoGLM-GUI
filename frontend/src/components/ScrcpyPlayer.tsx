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

  useEffect(() => {
    let reconnectTimeout: NodeJS.Timeout | null = null;

    const connect = () => {
      if (!videoRef.current) return;

      setStatus('connecting');
      setErrorMessage(null);

      try {
        // Initialize jMuxer with optimized settings
        jmuxerRef.current = new jMuxer({
          node: videoRef.current,
          mode: 'video',
          flushingTime: 100, // Small buffer to handle jitter
          fps: 30,
          debug: true,
          clearBuffer: false, // Don't clear buffer on errors
          onError: (error: any) => {
            console.error('[jMuxer] Decoder error:', error);
            // Just log the error, don't fail immediately
            // The decoder will try to recover automatically
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
              if (onFallback) {
                onFallback();
              }
            }
          }, fallbackTimeout);
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
              if (onFallback && !hasReceivedDataRef.current) {
                onFallback();
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
  }, [fallbackTimeout, onFallback]);

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
