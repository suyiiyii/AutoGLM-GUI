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
  Fingerprint,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  History,
  ListChecks,
  Square,
} from 'lucide-react';
import { throttle } from 'lodash';
import { ScrcpyPlayer } from './ScrcpyPlayer';
import type {
  ScreenshotResponse,
  ThinkingChunkEvent,
  StepEvent,
  DoneEvent,
  ErrorEvent,
  Workflow,
} from '../api';
import {
  abortChat,
  getScreenshot,
  initAgent,
  resetChat,
  sendMessageStream,
  listWorkflows,
} from '../api';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useTranslation } from '../lib/i18n-context';
import {
  createHistoryItem,
  saveHistoryItem,
  loadHistoryItems,
  clearHistory,
  deleteHistoryItem,
} from '../utils/history';
import type { HistoryItem } from '../types/history';
import { HistoryItemCard } from './HistoryItemCard';

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
  currentThinking?: string; // Current thinking text being streamed
}

interface GlobalConfig {
  base_url: string;
  model_name: string;
  api_key?: string;
}

interface DevicePanelProps {
  deviceId: string; // Used for API calls
  deviceSerial: string; // Used for history storage
  deviceName: string;
  config: GlobalConfig | null;
  isVisible: boolean;
  isConfigured: boolean;
}

export function DevicePanel({
  deviceId,
  deviceSerial,
  deviceName,
  config,
  isConfigured,
}: DevicePanelProps) {
  const t = useTranslation();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [aborting, setAborting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);
  const [screenshot, setScreenshot] = useState<ScreenshotResponse | null>(null);
  const [useVideoStream, setUseVideoStream] = useState(true);
  const [videoStreamFailed, setVideoStreamFailed] = useState(false);
  const [displayMode, setDisplayMode] = useState<
    'auto' | 'video' | 'screenshot'
  >('auto');
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [feedbackType, setFeedbackType] = useState<
    'tap' | 'swipe' | 'error' | 'success'
  >('success');
  const [showHistoryPopover, setShowHistoryPopover] = useState(false);
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [showWorkflowPopover, setShowWorkflowPopover] = useState(false);
  const feedbackTimeoutRef = useRef<number | null>(null);

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

  useEffect(() => {
    return () => {
      if (feedbackTimeoutRef.current) {
        clearTimeout(feedbackTimeoutRef.current);
      }
    };
  }, []);

  const [showControlArea, setShowControlArea] = useState(false);
  const [showControls, setShowControls] = useState(false);
  const controlsTimeoutRef = useRef<number | null>(null);

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

  useEffect(() => {
    return () => {
      if (controlsTimeoutRef.current) {
        clearTimeout(controlsTimeoutRef.current);
      }
    };
  }, []);

  const toggleControls = () => {
    setShowControls(prev => !prev);
  };

  const chatStreamRef = useRef<{ close: () => void } | null>(null);
  const videoStreamRef = useRef<{ close: () => void } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const screenshotFetchingRef = useRef(false);
  const hasAutoInited = useRef(false);
  const prevConfigRef = useRef<GlobalConfig | null>(null);
  const prevMessageCountRef = useRef(0);
  const prevMessageSigRef = useRef<string | null>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [showNewMessageNotice, setShowNewMessageNotice] = useState(false);

  // Create throttled scroll handler ref that persists across renders
  const throttledUpdateScrollStateRef = useRef(
    throttle(() => {
      const container = messagesContainerRef.current;
      if (!container) return;
      const threshold = 80;
      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      // Consider the user "at bottom" only when they are effectively at the end
      // of the scroll area, to avoid unwanted auto-scrolling when they have
      // intentionally scrolled slightly up.
      const atBottom = distanceFromBottom <= 1;
      setIsAtBottom(atBottom);
      // Still hide the new message notice when the user is near the bottom,
      // using the more generous threshold.
      if (distanceFromBottom <= threshold) {
        setShowNewMessageNotice(false);
      }
    }, 100)
  );

  // Cleanup throttled function on unmount
  useEffect(() => {
    const throttledFn = throttledUpdateScrollStateRef.current;
    return () => {
      throttledFn.cancel();
    };
  }, []);

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

  // Load history items when popover opens
  useEffect(() => {
    if (showHistoryPopover) {
      const items = loadHistoryItems(deviceSerial);
      setHistoryItems(items);
    }
  }, [showHistoryPopover, deviceSerial]);

  const handleSelectHistory = (item: HistoryItem) => {
    const userMessage: Message = {
      id: `${item.id}-user`,
      role: 'user',
      content: item.taskText,
      timestamp: item.startTime,
    };
    const agentMessage: Message = {
      id: `${item.id}-agent`,
      role: 'agent',
      content: item.finalMessage,
      timestamp: item.endTime,
      steps: item.steps,
      success: item.success,
      thinking: item.thinking,
      actions: item.actions,
      isStreaming: false,
    };
    const newMessages = [userMessage, agentMessage];
    setMessages(newMessages);

    // Reset previous message tracking refs to match the loaded history
    // so that the next effect run does not treat this as a new message.
    prevMessageCountRef.current = newMessages.length;
    prevMessageSigRef.current = [
      agentMessage.id,
      agentMessage.content?.length ?? 0,
      agentMessage.currentThinking?.length ?? 0,
      agentMessage.thinking ? JSON.stringify(agentMessage.thinking).length : 0,
      agentMessage.steps ?? '',
      agentMessage.isStreaming ? 1 : 0,
    ].join('|');

    setShowNewMessageNotice(false);
    setIsAtBottom(true);
    setShowHistoryPopover(false);
  };

  const handleClearHistory = () => {
    if (confirm(t.history.clearAllConfirm)) {
      clearHistory(deviceSerial);
      setHistoryItems([]);
    }
  };

  const handleDeleteItem = (itemId: string) => {
    deleteHistoryItem(deviceSerial, itemId);
    // 从列表中移除已删除的项
    setHistoryItems(prev => prev.filter(item => item.id !== itemId));
  };

  // Re-initialize when config changes (for already initialized devices)
  useEffect(() => {
    // Skip if not initialized yet or no config
    if (!initialized || !config) return;

    // Check if config actually changed
    const prevConfig = prevConfigRef.current;
    if (
      prevConfig &&
      (prevConfig.base_url !== config.base_url ||
        prevConfig.model_name !== config.model_name ||
        prevConfig.api_key !== config.api_key)
    ) {
      // Config changed, re-initialize
      console.log(
        `[DevicePanel] Config changed for device ${deviceId}, re-initializing...`
      );
      handleInit();
    }

    // Update previous config
    prevConfigRef.current = config;
  }, [config, initialized, deviceId, handleInit]);

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
    let currentThinkingText = '';
    // Use a ref to batch updates and reduce render frequency
    const thinkingChunksBuffer: string[] = [];
    let updateTimeoutId: number | null = null;

    const agentMessageId = (Date.now() + 1).toString();
    const agentMessage: Message = {
      id: agentMessageId,
      role: 'agent',
      content: '',
      timestamp: new Date(),
      thinking: [],
      actions: [],
      isStreaming: true,
      currentThinking: '',
    };

    setMessages(prev => [...prev, agentMessage]);

    // Batch update function to improve performance
    const flushThinkingUpdate = () => {
      if (thinkingChunksBuffer.length > 0) {
        const chunksToAdd = thinkingChunksBuffer.join('');
        thinkingChunksBuffer.length = 0; // Clear buffer
        currentThinkingText += chunksToAdd;

        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  currentThinking: currentThinkingText,
                }
              : msg
          )
        );
      }
      updateTimeoutId = null;
    };

    const stream = sendMessageStream(
      userMessage.content,
      deviceId,
      (event: ThinkingChunkEvent) => {
        // Buffer chunks and batch update every 50ms to reduce render frequency
        thinkingChunksBuffer.push(event.chunk);

        if (updateTimeoutId === null) {
          updateTimeoutId = setTimeout(flushThinkingUpdate, 50);
        }
      },
      (event: StepEvent) => {
        // Flush any remaining chunks before processing step
        if (updateTimeoutId !== null) {
          clearTimeout(updateTimeoutId);
          flushThinkingUpdate();
        }

        // Prefer backend-provided thinking as source of truth, fall back to streamed text
        const stepThinking =
          event.thinking && event.thinking.length > 0
            ? event.thinking
            : currentThinkingText;
        if (stepThinking) {
          thinkingList.push(stepThinking);
        }
        currentThinkingText = '';
        actionsList.push(event.action);

        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  thinking: [...thinkingList],
                  actions: [...actionsList],
                  steps: event.step,
                  currentThinking: '',
                }
              : msg
          )
        );
      },
      (event: DoneEvent) => {
        // Clear any pending updates
        if (updateTimeoutId !== null) {
          clearTimeout(updateTimeoutId);
        }

        const updatedAgentMessage = {
          ...agentMessage,
          content: event.message,
          success: event.success,
          isStreaming: false,
          steps: event.steps,
          thinking: [...thinkingList],
          actions: [...actionsList],
          timestamp: new Date(),
          currentThinking: undefined,
        };

        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId ? updatedAgentMessage : msg
          )
        );
        setLoading(false);
        chatStreamRef.current = null;

        // 保存到历史记录
        const historyItem = createHistoryItem(
          deviceSerial,
          deviceName,
          userMessage,
          updatedAgentMessage
        );
        saveHistoryItem(deviceSerial, historyItem);
      },
      (event: ErrorEvent) => {
        // Clear any pending updates
        if (updateTimeoutId !== null) {
          clearTimeout(updateTimeoutId);
        }

        const updatedAgentMessage = {
          ...agentMessage,
          content: `Error: ${event.message}`,
          success: false,
          isStreaming: false,
          thinking: [...thinkingList],
          actions: [...actionsList],
          timestamp: new Date(),
          currentThinking: undefined,
        };

        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId ? updatedAgentMessage : msg
          )
        );
        setLoading(false);
        setError(event.message);
        chatStreamRef.current = null;

        // 保存失败的任务到历史记录
        const historyItem = createHistoryItem(
          deviceSerial,
          deviceName,
          userMessage,
          updatedAgentMessage
        );
        saveHistoryItem(deviceSerial, historyItem);
      },
      (event: { type: 'aborted'; message: string }) => {
        // Clear any pending updates
        if (updateTimeoutId !== null) {
          clearTimeout(updateTimeoutId);
        }

        const updatedAgentMessage = {
          ...agentMessage,
          content: event.message || 'Chat aborted by user',
          success: false,
          isStreaming: false,
          thinking: [...thinkingList],
          actions: [...actionsList],
          timestamp: new Date(),
          currentThinking: undefined,
        };

        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId ? updatedAgentMessage : msg
          )
        );
        setLoading(false);
        chatStreamRef.current = null;

        // Show feedback
        setFeedbackMessage(t.chat.aborted);
        setFeedbackType('success');
        setTimeout(() => setFeedbackMessage(null), 2000);
      }
    );

    chatStreamRef.current = stream;
  }, [
    input,
    loading,
    initialized,
    deviceId,
    deviceSerial,
    deviceName,
    handleInit,
    t,
    setFeedbackMessage,
    setFeedbackType,
  ]);

  const handleReset = useCallback(async () => {
    if (chatStreamRef.current) {
      chatStreamRef.current.close();
    }

    setMessages([]);
    setLoading(false);
    setError(null);
    setShowNewMessageNotice(false);
    setIsAtBottom(true);
    chatStreamRef.current = null;
    prevMessageCountRef.current = 0;
    prevMessageSigRef.current = null;

    await resetChat(deviceId);
  }, [deviceId]);

  const handleAbortChat = useCallback(async () => {
    if (!chatStreamRef.current) return;

    setAborting(true);

    try {
      // Close SSE connection
      chatStreamRef.current.close();
      chatStreamRef.current = null;

      // Notify backend to abort
      await abortChat(deviceId);

      // Show feedback
      setFeedbackMessage(t.chat.aborted);
      setFeedbackType('success');
      setTimeout(() => setFeedbackMessage(null), 2000);
    } catch (error) {
      console.error('Failed to abort chat:', error);
      setFeedbackMessage(t.chat.abortFailed);
      setFeedbackType('error');
      setTimeout(() => setFeedbackMessage(null), 2000);
    } finally {
      setLoading(false);
      setAborting(false);
    }
  }, [deviceId, t]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    const latest = messages[messages.length - 1];
    const thinkingSignature = latest?.thinking
      ? JSON.stringify(latest.thinking).length
      : 0;
    const latestSignature = latest
      ? [
          latest.id,
          latest.content?.length ?? 0,
          latest.currentThinking?.length ?? 0,
          thinkingSignature,
          latest.steps ?? '',
          latest.isStreaming ? 1 : 0,
        ].join('|')
      : null;

    const isNewMessage = messages.length > prevMessageCountRef.current;
    const hasLatestChanged =
      latestSignature !== prevMessageSigRef.current && messages.length > 0;

    prevMessageCountRef.current = messages.length;
    prevMessageSigRef.current = latestSignature;

    if (isAtBottom) {
      scrollToBottom();
      setShowNewMessageNotice(false);
      return;
    }

    if (messages.length === 0) {
      setShowNewMessageNotice(false);
      return;
    }

    if (isNewMessage || hasLatestChanged) {
      setShowNewMessageNotice(true);
    }
  }, [messages, isAtBottom, scrollToBottom]);

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

  // Load workflows
  useEffect(() => {
    const loadWorkflows = async () => {
      try {
        const data = await listWorkflows();
        setWorkflows(data.workflows);
      } catch (error) {
        console.error('Failed to load workflows:', error);
      }
    };
    loadWorkflows();
  }, []);

  const handleExecuteWorkflow = (workflow: Workflow) => {
    setInput(workflow.text);
    setShowWorkflowPopover(false);
  };

  // Throttle scroll event handler to reduce the frequency of state updates
  // and improve performance, especially on lower-end devices
  const handleMessagesScroll = () => {
    throttledUpdateScrollStateRef.current();
  };

  const handleScrollToLatest = () => {
    scrollToBottom();
    setShowNewMessageNotice(false);
    setIsAtBottom(true);
  };

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
            {/* History button with Popover */}
            <Popover
              open={showHistoryPopover}
              onOpenChange={setShowHistoryPopover}
            >
              <PopoverTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 rounded-full text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300"
                  title={t.history.title}
                >
                  <History className="h-4 w-4" />
                </Button>
              </PopoverTrigger>

              <PopoverContent className="w-96 p-0" align="end" sideOffset={8}>
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800">
                  <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                    {t.history.title}
                  </h3>
                  {historyItems.length > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleClearHistory}
                      className="h-7 text-xs"
                    >
                      {t.history.clearAll}
                    </Button>
                  )}
                </div>

                {/* Scrollable content */}
                <ScrollArea className="h-[400px]">
                  <div className="p-4 space-y-2">
                    {historyItems.length > 0 ? (
                      historyItems.map(item => (
                        <HistoryItemCard
                          key={item.id}
                          item={item}
                          onSelect={handleSelectHistory}
                          onDelete={handleDeleteItem}
                        />
                      ))
                    ) : (
                      <div className="text-center py-8">
                        <History className="h-12 w-12 text-slate-300 dark:text-slate-700 mx-auto mb-3" />
                        <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                          {t.history.noHistory}
                        </p>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                          {t.history.noHistoryDescription}
                        </p>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </PopoverContent>
            </Popover>

            {!isConfigured ? (
              <Badge variant="warning">
                <AlertCircle className="w-3 h-3 mr-1" />
                {t.devicePanel.noConfig}
              </Badge>
            ) : !initialized ? (
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
        <div className="flex-1 min-h-0 relative">
          <div
            className="h-full overflow-y-auto p-4"
            ref={messagesContainerRef}
            onScroll={handleMessagesScroll}
          >
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center min-h-[calc(100%-1rem)]">
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
            ) : (
              messages.map(message => (
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
                          <p className="text-sm whitespace-pre-wrap text-slate-700 dark:text-slate-300">
                            {think}
                          </p>

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

                      {/* Current thinking being streamed */}
                      {message.currentThinking && (
                        <div className="bg-slate-100 dark:bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-3">
                          <div className="flex items-center gap-2 mb-2">
                            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#1d9bf0]/10">
                              <Sparkles className="h-3 w-3 text-[#1d9bf0] animate-pulse" />
                            </div>
                            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                              Thinking...
                            </span>
                          </div>
                          <p className="text-sm whitespace-pre-wrap text-slate-700 dark:text-slate-300">
                            {message.currentThinking}
                            <span className="inline-block w-1 h-4 ml-0.5 bg-[#1d9bf0] animate-pulse" />
                          </p>
                        </div>
                      )}

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
                              <p className="text-xs mt-2 opacity-60 text-slate-500 dark:text-slate-400">
                                {message.steps} steps completed
                              </p>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Streaming indicator */}
                      {message.isStreaming && (
                        <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
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
                      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 text-right">
                        {message.timestamp.toLocaleTimeString()}
                      </p>
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>
          {showNewMessageNotice && (
            <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
              <Button
                onClick={handleScrollToLatest}
                size="sm"
                className="pointer-events-auto shadow-lg bg-[#1d9bf0] text-white hover:bg-[#1a8cd8]"
                aria-label={t.devicePanel.newMessages}
              >
                {t.devicePanel.newMessages}
              </Button>
            </div>
          )}
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
            {/* Workflow Quick Run Button */}
            <Popover
              open={showWorkflowPopover}
              onOpenChange={setShowWorkflowPopover}
            >
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-10 w-10 flex-shrink-0"
                >
                  <ListChecks className="w-4 h-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-72 p-3">
                <div className="space-y-2">
                  <h4 className="font-medium text-sm">
                    {t.workflows.selectWorkflow}
                  </h4>
                  {workflows.length === 0 ? (
                    <div className="text-sm text-slate-500 dark:text-slate-400 space-y-1">
                      <p>{t.workflows.empty}</p>
                      <p>
                        前往{' '}
                        <a href="/workflows" className="text-primary underline">
                          工作流
                        </a>{' '}
                        页面创建。
                      </p>
                    </div>
                  ) : (
                    <ScrollArea className="h-64">
                      <div className="space-y-1">
                        {workflows.map(workflow => (
                          <button
                            key={workflow.uuid}
                            onClick={() => handleExecuteWorkflow(workflow)}
                            className="w-full text-left p-2 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                          >
                            <div className="font-medium text-sm">
                              {workflow.name}
                            </div>
                            <div className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                              {workflow.text}
                            </div>
                          </button>
                        ))}
                      </div>
                    </ScrollArea>
                  )}
                </div>
              </PopoverContent>
            </Popover>
            {/* Abort Button - shown when loading */}
            {loading && (
              <Button
                onClick={handleAbortChat}
                disabled={aborting}
                size="icon"
                variant="destructive"
                className="h-10 w-10 rounded-full flex-shrink-0"
                title={t.chat.abortChat}
              >
                {aborting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Square className="h-4 w-4" />
                )}
              </Button>
            )}
            {/* Send Button */}
            {!loading && (
              <Button
                onClick={handleSend}
                disabled={!input.trim()}
                size="icon"
                variant="twitter"
                className="h-10 w-10 rounded-full flex-shrink-0"
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Screen preview - phone aspect ratio */}
      <Card
        className="w-[320px] flex-shrink-0 relative min-h-0 overflow-hidden bg-background"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {/* Toggle and controls - shown on hover */}
        <div
          className={`absolute top-4 right-4 z-10 transition-opacity duration-200 ${
            showControlArea ? 'opacity-100' : 'opacity-0 pointer-events-none'
          }`}
        >
          <div className="flex items-center gap-2">
            {/* Control buttons - slide in/out */}
            <div
              className={`flex items-center gap-1 bg-popover/90 backdrop-blur rounded-xl p-1 shadow-lg border border-border transition-all duration-300 ${
                showControls
                  ? 'opacity-100 translate-x-0'
                  : 'opacity-0 translate-x-4 pointer-events-none'
              }`}
            >
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
                {t.devicePanel.auto}
              </Button>
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
                {t.devicePanel.video}
              </Button>
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
                {t.devicePanel.image}
              </Button>
            </div>

            {/* Toggle button - visible when control area is shown */}
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
            onTapSuccess={() => showFeedback(t.devicePanel.tapped, 2000, 'tap')}
            onTapError={error =>
              showFeedback(
                t.devicePanel.tapError.replace('{error}', error),
                3000,
                'error'
              )
            }
            onSwipeSuccess={() =>
              showFeedback(t.devicePanel.swiped, 2000, 'swipe')
            }
            onSwipeError={error =>
              showFeedback(
                t.devicePanel.swipeError.replace('{error}', error),
                3000,
                'error'
              )
            }
            onStreamReady={handleVideoStreamReady}
            fallbackTimeout={100000}
          />
        ) : (
          /* Screenshot mode */
          <div className="w-full h-full flex items-center justify-center bg-muted/30 min-h-0">
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
              <div className="text-center text-destructive">
                <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                <p className="font-medium">{t.devicePanel.screenshotFailed}</p>
                <p className="text-xs mt-1 opacity-60">{screenshot.error}</p>
              </div>
            ) : (
              <div className="text-center text-muted-foreground">
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
