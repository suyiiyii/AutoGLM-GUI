import React, { useRef, useEffect, useCallback, useState } from 'react';
import {
  Send,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  Video,
  Image as ImageIcon,
  MonitorPlay,
} from 'lucide-react';
import { ScrcpyPlayer } from './ScrcpyPlayer';
import type {
  ScreenshotResponse,
  StepEvent,
  DoneEvent,
  ErrorEvent,
} from '../api';
import { getScreenshot, initAgent, resetChat, sendMessageStream } from '../api';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { useTranslation } from '../lib/i18n-context';

interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: Date;
  steps?: number;
  success?: boolean;
  thinking?: string[];
  actions?: Record<string, unknown>[];
  isStreaming?: boolean;
}

interface GlobalConfig {
  base_url: string;
  model_name: string;
  api_key?: string;
}

interface DevicePanelProps {
  deviceId: string;
  deviceName: string;
  config: GlobalConfig | null;
  isVisible: boolean;
  isConfigured: boolean;
}

export function DevicePanel({
  deviceId,
  deviceName,
  config,
  isConfigured,
}: DevicePanelProps) {
  const t = useTranslation();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);
  const [screenshot, setScreenshot] = useState<ScreenshotResponse | null>(null);
  const [useVideoStream, setUseVideoStream] = useState(true);
  const [videoStreamFailed, setVideoStreamFailed] = useState(false);
  const [displayMode, setDisplayMode] = useState<
    'auto' | 'video' | 'screenshot'
  >('auto');
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const feedbackTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const showFeedback = (message: string, duration = 2000) => {
    if (feedbackTimeoutRef.current) {
      clearTimeout(feedbackTimeoutRef.current);
    }
    setFeedbackMessage(message);
    feedbackTimeoutRef.current = setTimeout(() => {
      setFeedbackMessage(null);
    }, duration);
  };

  useEffect(() => {
    return () => {
      if (feedbackTimeoutRef.current) {
        clearTimeout(feedbackTimeoutRef.current);
      }
    };
  }, []);

  const controlsTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleMouseEnter = () => {
    if (controlsTimeoutRef.current) {
      clearTimeout(controlsTimeoutRef.current);
    }
    setShowControls(true);
  };

  const handleMouseLeave = () => {
    controlsTimeoutRef.current = setTimeout(() => {
      setShowControls(false);
    }, 500);
  };

  useEffect(() => {
    return () => {
      if (controlsTimeoutRef.current) {
        clearTimeout(controlsTimeoutRef.current);
      }
    };
  }, []);

  const [showControls, setShowControls] = useState(false);

  const chatStreamRef = useRef<{ close: () => void } | null>(null);
  const videoStreamRef = useRef<{ close: () => void } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const screenshotFetchingRef = useRef(false);
  const hasAutoInited = useRef(false);

  const handleInit = useCallback(async () => {
    if (!config) return;

    try {
      await initAgent({
        model_config: {
          base_url: config.base_url || undefined,
          api_key: config.api_key || undefined,
          model_name: config.model_name || undefined,
        },
        agent_config: {
          device_id: deviceId,
        },
      });
      setInitialized(true);
      setError(null);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : 'Initialization failed';
      setError(errorMessage);
    }
  }, [deviceId, config]);

  // Auto-initialize on mount if configured
  useEffect(() => {
    if (isConfigured && config && !initialized && !hasAutoInited.current) {
      hasAutoInited.current = true;
      handleInit();
    }
  }, [isConfigured, config, initialized, handleInit]);

  const handleSend = useCallback(async () => {
    const inputValue = input.trim();
    if (!inputValue || loading) return;

    if (!initialized) {
      await handleInit();
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setError(null);

    const thinkingList: string[] = [];
    const actionsList: Record<string, unknown>[] = [];

    const agentMessageId = (Date.now() + 1).toString();
    const agentMessage: Message = {
      id: agentMessageId,
      role: 'agent',
      content: '',
      timestamp: new Date(),
      thinking: [],
      actions: [],
      isStreaming: true,
    };

    setMessages(prev => [...prev, agentMessage]);

    const stream = sendMessageStream(
      userMessage.content,
      deviceId,
      (event: StepEvent) => {
        thinkingList.push(event.thinking);
        actionsList.push(event.action);

        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  thinking: [...thinkingList],
                  actions: [...actionsList],
                  steps: event.step,
                }
              : msg
          )
        );
      },
      (event: DoneEvent) => {
        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  content: event.message,
                  success: event.success,
                  isStreaming: false,
                }
              : msg
          )
        );
        setLoading(false);
        chatStreamRef.current = null;
      },
      (event: ErrorEvent) => {
        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  content: `Error: ${event.message}`,
                  success: false,
                  isStreaming: false,
                }
              : msg
          )
        );
        setLoading(false);
        setError(event.message);
        chatStreamRef.current = null;
      }
    );

    chatStreamRef.current = stream;
  }, [input, loading, initialized, deviceId, handleInit]);

  const handleReset = useCallback(async () => {
    if (chatStreamRef.current) {
      chatStreamRef.current.close();
    }

    setMessages([]);
    setLoading(false);
    setError(null);
    chatStreamRef.current = null;

    await resetChat(deviceId);
  }, [deviceId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    return () => {
      if (chatStreamRef.current) {
        chatStreamRef.current.close();
      }
      if (videoStreamRef.current) {
        videoStreamRef.current.close();
      }
    };
  }, [deviceId]);

  useEffect(() => {
    if (!deviceId) return;

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
  }, [deviceId, videoStreamFailed, displayMode]);

  const handleInputKeyDown = (
    event: React.KeyboardEvent<HTMLTextAreaElement>
  ) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      handleSend();
    }
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

  return (
    <div className="flex-1 flex gap-4 p-4 items-stretch justify-center min-h-0">
      {/* Chat area - takes remaining space */}
      <Card className="flex-1 flex flex-col min-h-0 max-w-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#1d9bf0]/10">
              <Sparkles className="h-5 w-5 text-[#1d9bf0]" />
            </div>
            <div>
              <h2 className="font-bold text-slate-900 dark:text-slate-100">
                {deviceName}
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 font-mono">
                {deviceId}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!isConfigured && (
              <Badge variant="warning">
                <AlertCircle className="w-3 h-3 mr-1" />
                {t.devicePanel.noConfig}
              </Badge>
            )}

            {!initialized ? (
              <Button
                onClick={handleInit}
                disabled={!isConfigured || !config}
                size="sm"
                variant="twitter"
              >
                {t.devicePanel.initializing}
              </Button>
            ) : (
              <Badge variant="success">
                <CheckCircle2 className="w-3 h-3 mr-1" />
                {t.devicePanel.ready}
              </Badge>
            )}

            <Button
              variant="ghost"
              size="icon"
              onClick={handleReset}
              className="h-8 w-8 rounded-full text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300"
              title="Reset chat"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Error message */}
        {error && (
          <div className="mx-4 mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
          <div className="w-full">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 mb-4">
                  <Sparkles className="h-8 w-8 text-slate-400" />
                </div>
                <p className="font-medium text-slate-900 dark:text-slate-100">
                  {t.devicePanel.readyToHelp}
                </p>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                  {t.devicePanel.describeTask}
                </p>
              </div>
            ) : null}

            {messages.map(message => (
              <div
                key={message.id}
                className={`flex ${
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                {message.role === 'agent' ? (
                  <div className="max-w-[85%] space-y-3">
                    {/* Thinking process */}
                    {message.thinking?.map((think, idx) => (
                      <div
                        key={idx}
                        className="bg-slate-100 dark:bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-3"
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#1d9bf0]/10">
                            <Sparkles className="h-3 w-3 text-[#1d9bf0]" />
                          </div>
                          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                            Step {idx + 1}
                          </span>
                        </div>
                        <p className="text-sm whitespace-pre-wrap">{think}</p>

                        {message.actions?.[idx] && (
                          <details className="mt-2 text-xs">
                            <summary className="cursor-pointer text-[#1d9bf0] hover:text-[#1a8cd8]">
                              View action
                            </summary>
                            <pre className="mt-2 p-2 bg-slate-900 text-slate-200 rounded-lg overflow-x-auto text-xs">
                              {JSON.stringify(message.actions[idx], null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    ))}

                    {/* Final result */}
                    {message.content && (
                      <div
                        className={`
                        rounded-2xl px-4 py-3 flex items-start gap-2
                        ${
                          message.success === false
                            ? 'bg-red-100 dark:bg-red-900/20 text-red-600 dark:text-red-400'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                        }
                      `}
                      >
                        <CheckCircle2
                          className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                            message.success === false
                              ? 'text-red-500'
                              : 'text-green-500'
                          }`}
                        />
                        <div>
                          <p className="whitespace-pre-wrap">
                            {message.content}
                          </p>
                          {message.steps !== undefined && (
                            <p className="text-xs mt-2 opacity-60">
                              {message.steps} steps completed
                            </p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Streaming indicator */}
                    {message.isStreaming && (
                      <div className="flex items-center gap-2 text-sm text-slate-400">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Processing...
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="max-w-[75%]">
                    <div className="chat-bubble-user px-4 py-3">
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    </div>
                    <p className="text-xs text-slate-400 mt-1 text-right">
                      {message.timestamp.toLocaleTimeString()}
                    </p>
                  </div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input area */}
        <div className="p-4 border-t border-slate-200 dark:border-slate-800">
          <div className="flex items-end gap-3">
            <Textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder={
                !isConfigured
                  ? t.devicePanel.configureFirst
                  : !initialized
                    ? t.devicePanel.initDeviceFirst
                    : t.devicePanel.whatToDo
              }
              disabled={loading}
              className="flex-1 min-h-[40px] max-h-[120px] resize-none"
              rows={1}
            />
            <Button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              size="icon"
              variant="twitter"
              className="h-10 w-10 rounded-full flex-shrink-0"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </Card>

      {/* Screen preview - phone aspect ratio */}
      <Card
        className="w-[320px] flex-shrink-0 relative min-h-0 overflow-hidden bg-slate-950"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {/* Delayed controls - appears on hover */}
        <div
          className={`absolute top-4 right-4 z-10 transition-opacity duration-200 ${
            showControls ? 'opacity-100' : 'opacity-0 pointer-events-none'
          }`}
        >
          <div className="flex items-center gap-1 bg-slate-900/90 backdrop-blur rounded-xl p-1 shadow-lg">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => toggleDisplayMode('auto')}
              className={`h-7 px-3 text-xs rounded-lg transition-colors ${
                displayMode === 'auto'
                  ? 'bg-[#1d9bf0] text-white'
                  : 'text-slate-300 hover:text-white hover:bg-slate-800'
              }`}
            >
              {t.devicePanel.auto}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => toggleDisplayMode('video')}
              className={`h-7 px-3 text-xs rounded-lg transition-colors ${
                displayMode === 'video'
                  ? 'bg-[#1d9bf0] text-white'
                  : 'text-slate-300 hover:text-white hover:bg-slate-800'
              }`}
            >
              <Video className="w-3 h-3 mr-1" />
              {t.devicePanel.video}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => toggleDisplayMode('screenshot')}
              className={`h-7 px-3 text-xs rounded-lg transition-colors ${
                displayMode === 'screenshot'
                  ? 'bg-[#1d9bf0] text-white'
                  : 'text-slate-300 hover:text-white hover:bg-slate-800'
              }`}
            >
              <ImageIcon className="w-3 h-3 mr-1" />
              {t.devicePanel.image}
            </Button>
          </div>
        </div>

        {/* Current mode indicator - bottom left */}
        <div className="absolute bottom-4 left-4 z-10">
          <Badge
            variant="secondary"
            className="bg-slate-900/90 text-slate-300 border border-slate-700"
          >
            {displayMode === 'auto' && t.devicePanel.auto}
            {displayMode === 'video' && (
              <>
                <MonitorPlay className="w-3 h-3 mr-1" />
                {t.devicePanel.video}
              </>
            )}
            {displayMode === 'screenshot' && (
              <>
                <ImageIcon className="w-3 h-3 mr-1" />
                {t.devicePanel.imageRefresh}
              </>
            )}
          </Badge>
        </div>

        {/* Feedback message */}
        {feedbackMessage && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 px-3 py-2 bg-[#1d9bf0] text-white text-sm rounded-xl shadow-lg">
            {feedbackMessage}
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
            onTapSuccess={() => showFeedback(t.devicePanel.tapped, 2000)}
            onTapError={error =>
              showFeedback(
                t.devicePanel.tapError.replace('{error}', error),
                3000
              )
            }
            onSwipeSuccess={() => showFeedback(t.devicePanel.swiped, 2000)}
            onSwipeError={error =>
              showFeedback(
                t.devicePanel.swipeError.replace('{error}', error),
                3000
              )
            }
            onStreamReady={handleVideoStreamReady}
            fallbackTimeout={100000}
          />
        ) : (
          /* Screenshot mode */
          <div className="w-full h-full flex items-center justify-center bg-slate-900 min-h-0">
            {screenshot && screenshot.success ? (
              <div className="relative w-full h-full flex items-center justify-center min-h-0">
                <img
                  src={`data:image/png;base64,${screenshot.image}`}
                  alt="Device Screenshot"
                  className="max-w-full max-h-full object-contain"
                  style={{
                    width:
                      screenshot.width > screenshot.height ? '100%' : 'auto',
                    height:
                      screenshot.width > screenshot.height ? 'auto' : '100%',
                  }}
                />
                {screenshot.is_sensitive && (
                  <div className="absolute top-12 right-2 px-2 py-1 bg-yellow-500 text-white text-xs rounded-lg">
                    {t.devicePanel.sensitiveContent}
                  </div>
                )}
              </div>
            ) : screenshot?.error ? (
              <div className="text-center text-red-400">
                <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                <p className="font-medium">{t.devicePanel.screenshotFailed}</p>
                <p className="text-xs mt-1 opacity-60">{screenshot.error}</p>
              </div>
            ) : (
              <div className="text-center text-slate-400">
                <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin" />
                <p className="text-sm">{t.devicePanel.loading}</p>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
