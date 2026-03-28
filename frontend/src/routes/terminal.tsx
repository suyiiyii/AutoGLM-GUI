import { createFileRoute } from '@tanstack/react-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FitAddon } from '@xterm/addon-fit';
import { Terminal as XTerm } from '@xterm/xterm';
import {
  Loader2,
  MonitorSmartphone,
  RefreshCw,
  Terminal,
  Trash2,
} from 'lucide-react';

import '@xterm/xterm/css/xterm.css';

import {
  closeTerminalSession,
  createTerminalSession,
  getDevices,
  type Device,
  type TerminalSession,
} from '@/api';
import { Button } from '@/components/ui/button';
import { useTranslation } from '../lib/i18n-context';

export const Route = createFileRoute('/terminal')({
  component: TerminalRouteComponent,
});

function buildTerminalWebSocketUrl(
  sessionId: string,
  sessionToken: string
): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const query = new URLSearchParams({ token: sessionToken }).toString();
  return `${protocol}//${window.location.host}/api/terminal/sessions/${sessionId}/stream?${query}`;
}

function TerminalRouteComponent() {
  const t = useTranslation();
  const terminalContainerRef = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<XTerm | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const webSocketRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const sessionTokenRef = useRef<string | null>(null);

  const [isTerminalReady, setIsTerminalReady] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshingDevices, setIsRefreshingDevices] = useState(false);
  const [socketConnected, setSocketConnected] = useState(false);
  const [error, setError] = useState('');
  const [devices, setDevices] = useState<Device[]>([]);
  const [session, setSession] = useState<TerminalSession | null>(null);

  const statusTone = useMemo(() => {
    const status = session?.status || 'created';
    if (status === 'running') return 'text-emerald-600 bg-emerald-50';
    if (status === 'starting') return 'text-amber-600 bg-amber-50';
    if (status === 'closed') return 'text-slate-600 bg-slate-100';
    if (status === 'terminating') return 'text-orange-600 bg-orange-50';
    if (status === 'error') return 'text-red-600 bg-red-50';
    return 'text-slate-600 bg-slate-100';
  }, [session?.status]);

  const appendSystemMessage = useCallback((message: string) => {
    terminalRef.current?.writeln(`\r\n[AutoGLM] ${message}`);
  }, []);

  const sendResize = useCallback(() => {
    const terminal = terminalRef.current;
    const socket = webSocketRef.current;
    if (!terminal || !socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    socket.send(
      JSON.stringify({
        type: 'resize',
        cols: terminal.cols,
        rows: terminal.rows,
      })
    );
  }, []);

  const loadDevices = useCallback(async () => {
    try {
      setIsRefreshingDevices(true);
      const nextDevices = await getDevices();
      setDevices(nextDevices);
    } catch (loadError) {
      console.error('Failed to load devices:', loadError);
    } finally {
      setIsRefreshingDevices(false);
    }
  }, []);

  const closeCurrentSession = useCallback(async (clearState: boolean) => {
    const currentSessionId = sessionIdRef.current;
    const currentSessionToken = sessionTokenRef.current;

    if (webSocketRef.current) {
      webSocketRef.current.close();
      webSocketRef.current = null;
    }

    if (!currentSessionId || !currentSessionToken) {
      sessionIdRef.current = null;
      sessionTokenRef.current = null;
      if (clearState) {
        setSocketConnected(false);
        setSession(null);
      }
      return;
    }

    try {
      await closeTerminalSession(currentSessionId, currentSessionToken);
      sessionIdRef.current = null;
      sessionTokenRef.current = null;
    } catch (closeError) {
      console.error('Failed to close terminal session:', closeError);
    } finally {
      if (clearState) {
        setSocketConnected(false);
        setSession(null);
      }
    }
  }, []);

  const connectSessionStream = useCallback(
    (sessionId: string, sessionToken: string) => {
      const socket = new WebSocket(
        buildTerminalWebSocketUrl(sessionId, sessionToken)
      );
      webSocketRef.current = socket;

      socket.onopen = () => {
        setSocketConnected(true);
        sendResize();
        terminalRef.current?.focus();
      };

      socket.onmessage = event => {
        const payload = JSON.parse(event.data) as {
          type: string;
          data?: string;
          message?: string;
          status?: string;
          exit_code?: number;
        };

        if (payload.type === 'output' && payload.data) {
          terminalRef.current?.write(payload.data);
          return;
        }

        if (payload.type === 'status' && payload.status) {
          const nextStatus = payload.status;
          setSession(prev =>
            prev
              ? {
                  ...prev,
                  status: nextStatus,
                  last_active_at: Date.now() / 1000,
                }
              : prev
          );

          if (nextStatus === 'closed') {
            appendSystemMessage(t.terminal.sessionClosed);
          }
          return;
        }

        if (payload.type === 'exit') {
          appendSystemMessage(
            `${t.terminal.sessionClosed} (code ${payload.exit_code ?? 0})`
          );
          return;
        }

        if (payload.type === 'error' && payload.message) {
          setError(payload.message);
          appendSystemMessage(payload.message);
          return;
        }
      };

      socket.onerror = () => {
        setError(t.terminal.websocketFailed);
        appendSystemMessage(t.terminal.websocketFailed);
      };

      socket.onclose = () => {
        setSocketConnected(false);
      };
    },
    [
      appendSystemMessage,
      sendResize,
      t.terminal.sessionClosed,
      t.terminal.websocketFailed,
    ]
  );

  const createSession = useCallback(async () => {
    setIsLoading(true);
    setError('');

    await closeCurrentSession(false);
    sessionIdRef.current = null;
    sessionTokenRef.current = null;
    terminalRef.current?.clear();

    try {
      const nextSession = await createTerminalSession();
      sessionIdRef.current = nextSession.session_id;
      sessionTokenRef.current = nextSession.session_token;
      setSession(nextSession);
      connectSessionStream(nextSession.session_id, nextSession.session_token);
      appendSystemMessage(t.terminal.initialMessage);
    } catch (createError) {
      const message =
        createError instanceof Error
          ? createError.message
          : t.terminal.createFailed;
      setError(message);
      appendSystemMessage(message);
      sessionTokenRef.current = null;
      setSession(null);
    } finally {
      setIsLoading(false);
    }
  }, [
    appendSystemMessage,
    closeCurrentSession,
    connectSessionStream,
    t.terminal.createFailed,
    t.terminal.initialMessage,
  ]);

  const sendCommand = useCallback(
    (command: string) => {
      const socket = webSocketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        setError(t.terminal.websocketFailed);
        return;
      }

      socket.send(JSON.stringify({ type: 'input', data: command }));
      terminalRef.current?.focus();
    },
    [t.terminal.websocketFailed]
  );

  useEffect(() => {
    const terminalContainer = terminalContainerRef.current;
    if (!terminalContainer) {
      return undefined;
    }

    const terminal = new XTerm({
      cursorBlink: true,
      convertEol: true,
      fontFamily:
        '"SFMono-Regular", "JetBrains Mono", "Menlo", "Monaco", "Consolas", monospace',
      fontSize: 13,
      theme: {
        background: '#020617',
        foreground: '#e2e8f0',
        cursor: '#f8fafc',
        black: '#0f172a',
        blue: '#38bdf8',
        brightBlue: '#7dd3fc',
        brightCyan: '#67e8f9',
        brightGreen: '#86efac',
        brightMagenta: '#f9a8d4',
        brightRed: '#fca5a5',
        brightWhite: '#f8fafc',
        brightYellow: '#fde68a',
        cyan: '#22d3ee',
        green: '#4ade80',
        magenta: '#f472b6',
        red: '#f87171',
        white: '#e2e8f0',
        yellow: '#facc15',
      },
    });
    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(terminalContainer);
    fitAddon.fit();
    terminal.focus();

    const onDataDisposable = terminal.onData(data => {
      const socket = webSocketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        return;
      }

      socket.send(JSON.stringify({ type: 'input', data }));
    });

    const onResizeDisposable = terminal.onResize(({ cols, rows }) => {
      const socket = webSocketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        return;
      }

      socket.send(JSON.stringify({ type: 'resize', cols, rows }));
    });

    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit();
      sendResize();
    });
    resizeObserver.observe(terminalContainer);

    terminalRef.current = terminal;
    fitAddonRef.current = fitAddon;
    resizeObserverRef.current = resizeObserver;
    setIsTerminalReady(true);

    return () => {
      setIsTerminalReady(false);
      resizeObserver.disconnect();
      onDataDisposable.dispose();
      onResizeDisposable.dispose();
      terminal.dispose();
      resizeObserverRef.current = null;
      fitAddonRef.current = null;
      terminalRef.current = null;
    };
  }, [sendResize]);

  useEffect(() => {
    if (!isTerminalReady) {
      return undefined;
    }

    void createSession();
    void loadDevices();

    return () => {
      void closeCurrentSession(false);
    };
  }, [closeCurrentSession, createSession, isTerminalReady, loadDevices]);

  return (
    <div className="h-full flex bg-slate-100 dark:bg-slate-950">
      <div className="w-80 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-4 flex flex-col gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-sky-100 text-sky-600 dark:bg-sky-950/40 dark:text-sky-300">
              <Terminal className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                {t.terminal.title}
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {t.terminal.subtitle}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/60 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-[0.18em] text-slate-500">
              {t.terminal.statusLabel}
            </span>
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${statusTone}`}
            >
              {session?.status || 'created'}
            </span>
          </div>

          <div className="space-y-1 text-sm text-slate-600 dark:text-slate-300">
            <div>
              <span className="text-slate-400">
                {t.terminal.sessionLabel}:{' '}
              </span>
              <span className="font-mono break-all">
                {session?.session_id || '-'}
              </span>
            </div>
            <div>
              <span className="text-slate-400">{t.terminal.cwdLabel}: </span>
              <span className="font-mono break-all">{session?.cwd || '-'}</span>
            </div>
            <div>
              <span className="text-slate-400">
                {t.terminal.commandLabel}:{' '}
              </span>
              <span className="font-mono break-all">
                {session?.command.join(' ') || '-'}
              </span>
            </div>
            <div>
              <span className="text-slate-400">Socket: </span>
              <span>
                {socketConnected
                  ? t.terminal.socketConnected
                  : t.terminal.socketDisconnected}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Button onClick={() => void createSession()} disabled={isLoading}>
              {isLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              {session ? t.terminal.restartSession : t.terminal.newSession}
            </Button>
            <Button
              variant="outline"
              onClick={() => terminalRef.current?.clear()}
              disabled={!isTerminalReady}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              {t.terminal.clearScreen}
            </Button>
            <Button
              variant="outline"
              onClick={() => void closeCurrentSession(true)}
              disabled={!session}
              className="col-span-2"
            >
              {t.terminal.closeSession}
            </Button>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {t.terminal.quickActions}
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {t.terminal.connectedDevices}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => void loadDevices()}
              disabled={isRefreshingDevices}
              title={t.terminal.refreshDevices}
            >
              <RefreshCw
                className={`h-4 w-4 ${isRefreshingDevices ? 'animate-spin' : ''}`}
              />
            </Button>
          </div>

          <Button
            variant="outline"
            className="w-full justify-start"
            onClick={() => sendCommand('adb devices -l\n')}
            disabled={!session}
          >
            {t.terminal.adbDevices}
          </Button>

          <div className="space-y-2">
            {devices.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 dark:border-slate-800 p-4 text-sm text-slate-500 dark:text-slate-400">
                {t.terminal.noDevices}
              </div>
            ) : (
              devices.map(device => (
                <button
                  key={device.id}
                  type="button"
                  onClick={() => sendCommand(`adb -s ${device.id} shell\n`)}
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-800 p-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-900"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                      <MonitorSmartphone className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                        {device.display_name || device.model}
                      </div>
                      <div className="truncate font-mono text-xs text-slate-500 dark:text-slate-400">
                        {device.id}
                      </div>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 min-w-0 flex flex-col">
        {error && (
          <div className="m-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-300">
            {error}
          </div>
        )}

        <div className="relative mx-4 mt-4 flex-1 overflow-hidden border border-slate-200 dark:border-slate-800 bg-slate-950 shadow-[0_24px_80px_rgba(15,23,42,0.28)]">
          {!session && !isLoading && (
            <div className="absolute inset-x-0 top-20 z-10 mx-auto w-fit rounded-full bg-white/90 px-4 py-2 text-sm text-slate-600 shadow-sm backdrop-blur dark:bg-slate-900/80 dark:text-slate-300">
              {t.terminal.closedHint}
            </div>
          )}
          <div
            ref={terminalContainerRef}
            className="h-full w-full"
            aria-label={t.terminal.title}
          />
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm">
              <div className="flex items-center gap-3 rounded-full bg-slate-900/90 px-5 py-3 text-sm text-slate-100 shadow-lg">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t.terminal.emptyState}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
