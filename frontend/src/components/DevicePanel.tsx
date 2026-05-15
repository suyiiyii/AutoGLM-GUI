import React, { useRef, useEffect, useCallback, useState } from 'react';
import {
  Send,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  History,
  ListChecks,
  Loader2,
  Square,
  ImagePlus,
  X,
} from 'lucide-react';
import { DeviceMonitor } from './DeviceMonitor';
import type {
  StepTimingSummary,
  TaskImageAttachment,
  Workflow,
  HistoryRecordResponse,
} from '../api';
import {
  listWorkflows,
  listHistory,
  getHistoryRecord,
  clearHistory as clearHistoryApi,
  deleteHistoryRecord,
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
import { HistoryItemCard } from './HistoryItemCard';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { ImagePreview } from '@/components/ui/image-preview';
import {
  useTaskSessionConversation,
  type TaskConversationMessage,
} from '../hooks/useTaskSessionConversation';

interface ActionPayload {
  action?: string;
  element?: [number, number];
  start?: [number, number];
  end?: [number, number];
  [key: string]: unknown;
}

interface DevicePanelProps {
  deviceId: string; // Used for API calls
  deviceSerial: string; // Used for history storage
  deviceName: string;
  deviceConnectionType?: string; // Device connection type (usb/wifi/remote)
  isConfigured: boolean;
  isVisible?: boolean; // ✅ 新增：控制视频流行为
  unlimitedStepsEnabled?: boolean;
}

const IMAGE_ATTACHMENT_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
]);
const MAX_IMAGE_ATTACHMENTS = 3;
const MAX_IMAGE_ATTACHMENT_BYTES = 5 * 1024 * 1024;

function readImageAttachment(file: File): Promise<TaskImageAttachment> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('读取图片失败'));
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const commaIndex = result.indexOf(',');
      if (commaIndex === -1) {
        reject(new Error('图片格式无效'));
        return;
      }
      resolve({
        mime_type: file.type,
        data: result.slice(commaIndex + 1),
        name: file.name || null,
      });
    };
    reader.readAsDataURL(file);
  });
}

function getStepSummary(thinking: string | undefined, action: unknown): string {
  if (thinking && thinking.trim().length > 0) {
    return thinking;
  }

  if (action && typeof action === 'object') {
    const actionRecord = action as Record<string, unknown>;
    const metadata = actionRecord['_metadata'];

    if (metadata === 'finish') {
      const finishMessage = actionRecord['message'];
      if (
        typeof finishMessage === 'string' &&
        finishMessage.trim().length > 0
      ) {
        return `Finish: ${finishMessage}`;
      }
      return 'Finish task';
    }

    const actionName = actionRecord['action'];
    if (typeof actionName === 'string' && actionName.trim().length > 0) {
      return `Action: ${actionName}`;
    }
  }

  return 'Action executed';
}

function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

function getTimingChips(
  timings: StepTimingSummary | undefined
): Array<{ label: string; value: string }> {
  if (!timings) {
    return [];
  }

  const chips = [
    { label: 'Total', value: formatDuration(timings.total_duration_ms) },
    { label: 'LLM', value: formatDuration(timings.llm_duration_ms) },
  ];

  if (timings.screenshot_duration_ms > 0) {
    chips.push({
      label: 'Shot',
      value: formatDuration(timings.screenshot_duration_ms),
    });
  }

  if (timings.current_app_duration_ms > 0) {
    chips.push({
      label: 'App',
      value: formatDuration(timings.current_app_duration_ms),
    });
  }

  if (timings.execute_action_duration_ms > 0) {
    chips.push({
      label: 'Action',
      value: formatDuration(timings.execute_action_duration_ms),
    });
  }

  if (timings.sleep_duration_ms > 0) {
    chips.push({
      label: 'Sleep',
      value: formatDuration(timings.sleep_duration_ms),
    });
  }

  return chips;
}

export function DevicePanel({
  deviceId,
  deviceSerial,
  deviceName,
  deviceConnectionType,
  isConfigured,
  isVisible = true, // ✅ 新增：默认 true 向后兼容
  unlimitedStepsEnabled = false,
}: DevicePanelProps) {
  const t = useTranslation();
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<TaskImageAttachment[]>([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [isDraggingAttachment, setIsDraggingAttachment] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // ✅ 移除 initialized 状态，依赖后端自动初始化
  // const [initialized, setInitialized] = useState(false);
  const [showHistoryPopover, setShowHistoryPopover] = useState(false);
  const [historyItems, setHistoryItems] = useState<HistoryRecordResponse[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [showWorkflowPopover, setShowWorkflowPopover] = useState(false);
  const {
    messages,
    setMessages,
    loading,
    aborting,
    error,
    sessionReady,
    sendMessage,
    resetConversation,
    abortConversation,
  } = useTaskSessionConversation({
    deviceId,
    deviceSerial,
    sessionStorageKey: `autoglm:classic-session:${deviceSerial}`,
  });
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef(0);
  const prevMessageSigRef = useRef<string | null>(null);
  // The chat follows the latest message by default. Only a deliberate upward
  // scroll by the user turns this off — programmatic re-pins and content that
  // grows underneath (e.g. screenshots finishing decode) must never flip it,
  // otherwise the stale scroll events they emit would strand the view.
  const isAtBottomRef = useRef(true);
  // Timestamp of the last programmatic scroll-to-bottom. Scroll events that
  // land within this window are the echo of our own pinning (or of the layout
  // settling afterwards) and are ignored, not treated as the user leaving.
  const lastPinTimeRef = useRef(0);
  // Last observed scrollTop. Used to tell a real upward scroll (scrollTop
  // decreases) apart from content growing underneath (scrollTop stays put).
  const lastScrollTopRef = useRef(0);
  const [showNewMessageNotice, setShowNewMessageNotice] = useState(false);

  // The actual scrollable element lives inside the Radix ScrollArea.
  const getScrollViewport = useCallback(
    () =>
      (scrollAreaRef.current?.querySelector(
        '[data-slot="scroll-area-viewport"]'
      ) as HTMLDivElement | null) ?? null,
    []
  );

  const pinToBottom = useCallback(
    (behavior: 'auto' | 'smooth' = 'auto') => {
      const viewport = getScrollViewport();
      if (!viewport) return;
      lastPinTimeRef.current = performance.now();
      viewport.scrollTo({ top: viewport.scrollHeight, behavior });
    },
    [getScrollViewport]
  );

  // Step screenshots load asynchronously and grow the content after the
  // streaming effect already scrolled, which would otherwise leave the chat
  // parked a few hundred pixels above the latest message. A ResizeObserver
  // re-pins the view to the bottom whenever the content height changes while
  // the user is still following along.
  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    const observer = new ResizeObserver(() => {
      if (isAtBottomRef.current) {
        pinToBottom();
      }
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [pinToBottom]);

  // ✅ 移除 handleInit 函数，不再需要显式初始化
  // Agent 会在首次发送消息时自动初始化

  // ✅ 移除自动初始化 useEffect，不再需要

  // Load history items when popover opens
  useEffect(() => {
    if (showHistoryPopover) {
      const loadItems = async () => {
        try {
          const data = await listHistory(deviceSerial, 20, 0, 'classic');
          setHistoryItems(data.records);
        } catch (error) {
          console.error('Failed to load history:', error);
          setHistoryItems([]);
        }
      };
      loadItems();
    }
  }, [showHistoryPopover, deviceSerial]);

  const handleSelectHistory = (record: HistoryRecordResponse) => {
    void (async () => {
      let selectedRecord = record;
      try {
        selectedRecord = await getHistoryRecord(deviceSerial, record.id);
      } catch (error) {
        console.error('Failed to load history record detail:', error);
      }

      // Convert backend messages to frontend Message format
      const newMessages: TaskConversationMessage[] = [];

      // Find user message from record
      const userMsg = selectedRecord.messages.find(m => m.role === 'user');
      if (userMsg) {
        newMessages.push({
          id: `${selectedRecord.id}-user`,
          role: 'user',
          content: userMsg.content || selectedRecord.task_text,
          timestamp: new Date(userMsg.timestamp),
          attachments: userMsg.attachments || [],
        });
      } else {
        // Fallback to task_text if no user message
        newMessages.push({
          id: `${selectedRecord.id}-user`,
          role: 'user',
          content: selectedRecord.task_text,
          timestamp: new Date(selectedRecord.start_time),
        });
      }

      // Collect thinking and actions from assistant messages
      const thinkingList: string[] = [];
      const actionsList: Record<string, unknown>[] = [];
      const screenshotsList: (string | undefined)[] = [];
      selectedRecord.messages
        .filter(m => m.role === 'assistant')
        .forEach(m => {
          if (m.thinking) thinkingList.push(m.thinking);
          if (m.action) actionsList.push(m.action);
          // Extract screenshot directly or from loosely typed object
          const recordData = m as unknown as { screenshot?: string };
          screenshotsList.push(recordData.screenshot);
        });

      // Create agent message
      const agentMessage: TaskConversationMessage = {
        id: `${selectedRecord.id}-agent`,
        role: 'assistant',
        content: selectedRecord.final_message,
        timestamp: selectedRecord.end_time
          ? new Date(selectedRecord.end_time)
          : new Date(selectedRecord.start_time),
        steps: selectedRecord.steps,
        success: selectedRecord.success,
        thinking: thinkingList,
        actions: actionsList,
        screenshots: screenshotsList,
        stepTimings: selectedRecord.step_timings,
        isStreaming: false,
      };
      newMessages.push(agentMessage);

      setMessages(newMessages);

      // Reset previous message tracking refs to match the loaded history
      prevMessageCountRef.current = newMessages.length;
      prevMessageSigRef.current = [
        agentMessage.id,
        agentMessage.content?.length ?? 0,
        agentMessage.currentThinking?.length ?? 0,
        agentMessage.thinking
          ? JSON.stringify(agentMessage.thinking).length
          : 0,
        agentMessage.steps ?? '',
        agentMessage.isStreaming ? 1 : 0,
      ].join('|');

      setShowNewMessageNotice(false);
      isAtBottomRef.current = true;
      setShowHistoryPopover(false);
    })();
  };

  const handleClearHistory = async () => {
    if (confirm(t.history.clearAllConfirm)) {
      try {
        await clearHistoryApi(deviceSerial);
        setHistoryItems([]);
      } catch (error) {
        console.error('Failed to clear history:', error);
      }
    }
  };

  const handleDeleteItem = async (itemId: string) => {
    try {
      await deleteHistoryRecord(deviceSerial, itemId);
      // 从列表中移除已删除的项
      setHistoryItems(prev => prev.filter(item => item.id !== itemId));
    } catch (error) {
      console.error('Failed to delete history item:', error);
    }
  };

  // Note: Configuration is now managed entirely by backend ConfigManager.
  // If user updates config via Settings, they need to manually re-initialize agents.

  const addImageFiles = useCallback(
    async (files: File[]) => {
      const imageFiles = files.filter(file =>
        IMAGE_ATTACHMENT_TYPES.has(file.type)
      );
      if (imageFiles.length === 0) {
        return;
      }

      if (attachments.length + imageFiles.length > MAX_IMAGE_ATTACHMENTS) {
        setAttachmentError('最多只能附加 3 张图片');
        return;
      }

      const tooLargeFile = imageFiles.find(
        file => file.size > MAX_IMAGE_ATTACHMENT_BYTES
      );
      if (tooLargeFile) {
        setAttachmentError('单张图片不能超过 5 MiB');
        return;
      }

      try {
        const nextAttachments = await Promise.all(
          imageFiles.map(file => readImageAttachment(file))
        );
        setAttachments(current => [...current, ...nextAttachments]);
        setAttachmentError(null);
      } catch (readError) {
        setAttachmentError(
          readError instanceof Error ? readError.message : '读取图片失败'
        );
      }
    },
    [attachments.length]
  );

  const handleFileInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files || []);
      void addImageFiles(files);
      event.target.value = '';
    },
    [addImageFiles]
  );

  const handlePaste = useCallback(
    (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const files = Array.from(event.clipboardData.files || []);
      const hasImages = files.some(file =>
        IMAGE_ATTACHMENT_TYPES.has(file.type)
      );
      if (!hasImages) {
        return;
      }
      event.preventDefault();
      void addImageFiles(files);
    },
    [addImageFiles]
  );

  const handleDragOver = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      if (
        Array.from(event.dataTransfer.items || []).some(item =>
          IMAGE_ATTACHMENT_TYPES.has(item.type)
        )
      ) {
        event.preventDefault();
        setIsDraggingAttachment(true);
      }
    },
    []
  );

  const handleDragLeave = useCallback(() => {
    setIsDraggingAttachment(false);
  }, []);

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      const files = Array.from(event.dataTransfer.files || []);
      const hasImages = files.some(file =>
        IMAGE_ATTACHMENT_TYPES.has(file.type)
      );
      if (!hasImages) {
        return;
      }
      event.preventDefault();
      setIsDraggingAttachment(false);
      void addImageFiles(files);
    },
    [addImageFiles]
  );

  const removeAttachment = useCallback((index: number) => {
    setAttachments(current => current.filter((_, idx) => idx !== index));
  }, []);

  const handleSend = useCallback(async () => {
    const didSend = await sendMessage(input, attachments);
    if (didSend) {
      setInput('');
      setAttachments([]);
      setAttachmentError(null);
    }
  }, [attachments, input, sendMessage]);

  const handleReset = useCallback(async () => {
    await resetConversation();
    setShowNewMessageNotice(false);
    isAtBottomRef.current = true;
    prevMessageCountRef.current = 0;
    prevMessageSigRef.current = null;
    setAttachments([]);
    setAttachmentError(null);
  }, [resetConversation]);

  const handleAbortChat = useCallback(async () => {
    await abortConversation();
  }, [abortConversation]);

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

    if (isAtBottomRef.current) {
      pinToBottom();
      const frameId = requestAnimationFrame(() => {
        setShowNewMessageNotice(false);
      });
      return () => cancelAnimationFrame(frameId);
    }

    if (messages.length === 0) {
      const frameId = requestAnimationFrame(() => {
        setShowNewMessageNotice(false);
      });
      return () => cancelAnimationFrame(frameId);
    }

    if (isNewMessage || hasLatestChanged) {
      const frameId = requestAnimationFrame(() => {
        setShowNewMessageNotice(true);
      });
      return () => cancelAnimationFrame(frameId);
    }
  }, [messages, pinToBottom]);

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

  const handleMessagesScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const scrollTop = target.scrollTop;
    const prevScrollTop = lastScrollTopRef.current;
    lastScrollTopRef.current = scrollTop;

    // Ignore the scroll events caused by our own re-pinning and by the
    // re-layout that late-loading content (screenshots) triggers right after.
    if (performance.now() - lastPinTimeRef.current < 150) return;

    const distanceFromBottom =
      target.scrollHeight - scrollTop - target.clientHeight;
    // A generous band so a few hundred pixels of late-loading content between
    // streaming updates doesn't break following.
    if (distanceFromBottom < 150) {
      isAtBottomRef.current = true;
      setShowNewMessageNotice(false);
      return;
    }
    // Far from the bottom: only treat it as the user opting out if they
    // actually scrolled upward. Content growing or a programmatic re-pin keeps
    // (or raises) scrollTop, so the stale events they emit can't trip this.
    if (scrollTop < prevScrollTop - 4) {
      isAtBottomRef.current = false;
    }
  };

  const handleScrollToLatest = () => {
    isAtBottomRef.current = true;
    pinToBottom();
    setShowNewMessageNotice(false);
  };

  const handleInputKeyDown = (
    event: React.KeyboardEvent<HTMLTextAreaElement>
  ) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex-1 flex gap-4 p-4 items-stretch justify-center min-h-0">
      {/* Chat area - takes remaining space */}
      <Card className="flex-1 flex flex-col min-h-0 max-w-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#1d9bf0]/10">
              <Sparkles className="h-5 w-5 text-[#1d9bf0]" />
            </div>
            <div className="group">
              <div className="flex items-center gap-1">
                <h2 className="font-bold text-slate-900 dark:text-slate-100">
                  {deviceName}
                </h2>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 font-mono">
                {deviceId}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {loading && unlimitedStepsEnabled && (
              <Badge
                variant="secondary"
                className="bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
              >
                无限步数模式
              </Badge>
            )}
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

            {!isConfigured && (
              <Badge variant="warning">
                <AlertCircle className="w-3 h-3 mr-1" />
                {t.devicePanel.noConfig}
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
        {(error || attachmentError) && (
          <div className="mx-4 mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {error || attachmentError}
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 min-h-0 relative">
          <ScrollArea
            ref={scrollAreaRef}
            className="h-full"
            data-testid="chat-scroll-container"
            onScroll={handleMessagesScroll}
          >
            <div className="p-4" ref={contentRef}>
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
                    {message.role === 'assistant' ? (
                      <div className="max-w-[85%] space-y-3">
                        {/* Step process */}
                        {Array.from(
                          {
                            length: Math.max(
                              message.thinking?.length || 0,
                              message.actions?.length || 0
                            ),
                          },
                          (_, idx) => idx
                        ).map(idx => {
                          const stepThinking = message.thinking?.[idx];
                          const stepAction = message.actions?.[idx];
                          const stepScreenshot = message.screenshots?.[idx];
                          const stepTimings = message.stepTimings?.[idx];
                          const stepSummary = getStepSummary(
                            stepThinking,
                            stepAction
                          );

                          return (
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
                                {stepSummary}
                              </p>

                              {stepTimings && (
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {getTimingChips(stepTimings).map(chip => (
                                    <Badge
                                      key={`${idx}-${chip.label}`}
                                      variant="secondary"
                                      className="font-mono text-[11px]"
                                    >
                                      {chip.label} {chip.value}
                                    </Badge>
                                  ))}
                                </div>
                              )}

                              {stepScreenshot && (
                                <div className="mt-3">
                                  <ImagePreview
                                    src={`data:image/png;base64,${stepScreenshot}`}
                                    alt={`Step ${idx + 1}`}
                                    maxHeight="350px"
                                  >
                                    {stepAction &&
                                      (() => {
                                        const parsedAction =
                                          stepAction as ActionPayload;
                                        const actionName = parsedAction.action;

                                        if (
                                          actionName &&
                                          [
                                            'Tap',
                                            'Double Tap',
                                            'Long Press',
                                          ].includes(actionName)
                                        ) {
                                          const element = parsedAction.element;
                                          if (
                                            Array.isArray(element) &&
                                            element.length === 2
                                          ) {
                                            const left = `${(Math.max(0, Math.min(element[0], 1000)) / 1000) * 100}%`;
                                            const top = `${(Math.max(0, Math.min(element[1], 1000)) / 1000) * 100}%`;
                                            return (
                                              <div
                                                className="absolute w-8 h-8 rounded-full border-[3px] border-red-500 bg-red-500/20 transform -translate-x-1/2 -translate-y-1/2 pointer-events-none animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.6)]"
                                                style={{ left, top }}
                                              />
                                            );
                                          }
                                        }
                                        if (actionName === 'Swipe') {
                                          const start = parsedAction.start;
                                          const end = parsedAction.end;
                                          if (
                                            Array.isArray(start) &&
                                            start.length === 2 &&
                                            Array.isArray(end) &&
                                            end.length === 2
                                          ) {
                                            const x1 =
                                              (Math.max(
                                                0,
                                                Math.min(start[0], 1000)
                                              ) /
                                                1000) *
                                              100;
                                            const y1 =
                                              (Math.max(
                                                0,
                                                Math.min(start[1], 1000)
                                              ) /
                                                1000) *
                                              100;
                                            const x2 =
                                              (Math.max(
                                                0,
                                                Math.min(end[0], 1000)
                                              ) /
                                                1000) *
                                              100;
                                            const y2 =
                                              (Math.max(
                                                0,
                                                Math.min(end[1], 1000)
                                              ) /
                                                1000) *
                                              100;
                                            return (
                                              <svg className="absolute inset-0 w-full h-full pointer-events-none overflow-visible">
                                                <defs>
                                                  <marker
                                                    id={`arrowhead-${idx}`}
                                                    markerWidth="6"
                                                    markerHeight="6"
                                                    refX="5"
                                                    refY="3"
                                                    orient="auto"
                                                  >
                                                    <polygon
                                                      points="0,0 6,3 0,6"
                                                      fill="rgba(239,68,68,0.9)"
                                                    />
                                                  </marker>
                                                </defs>
                                                <circle
                                                  cx={`${x1}%`}
                                                  cy={`${y1}%`}
                                                  r="4"
                                                  fill="rgba(239,68,68,0.9)"
                                                />
                                                <line
                                                  x1={`${x1}%`}
                                                  y1={`${y1}%`}
                                                  x2={`${x2}%`}
                                                  y2={`${y2}%`}
                                                  stroke="rgba(239,68,68,0.9)"
                                                  strokeWidth="3"
                                                  markerEnd={`url(#arrowhead-${idx})`}
                                                  strokeDasharray="5 3"
                                                />
                                              </svg>
                                            );
                                          }
                                        }
                                        return null;
                                      })()}
                                  </ImagePreview>
                                </div>
                              )}

                              {stepAction && (
                                <details className="mt-2 text-xs">
                                  <summary className="cursor-pointer text-[#1d9bf0] hover:text-[#1a8cd8] transition-colors">
                                    View action
                                  </summary>
                                  <pre className="mt-2 p-2 bg-slate-900 text-slate-200 rounded-lg overflow-x-auto text-xs border border-slate-800">
                                    {JSON.stringify(stepAction, null, 2)}
                                  </pre>
                                </details>
                              )}
                            </div>
                          );
                        })}

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
                        <div className="chat-bubble-user px-4 py-3 space-y-2">
                          {message.attachments &&
                            message.attachments.length > 0 && (
                              <div className="grid grid-cols-2 gap-2">
                                {message.attachments.map((attachment, idx) => (
                                  <ImagePreview
                                    key={`${message.id}-attachment-${idx}`}
                                    src={`data:${attachment.mime_type};base64,${attachment.data}`}
                                    alt={
                                      attachment.name || `Attachment ${idx + 1}`
                                    }
                                    className="w-full border-white/20"
                                    thumbnailClassName="w-full object-cover"
                                    maxHeight="96px"
                                  />
                                ))}
                              </div>
                            )}
                          {message.content && (
                            <p className="whitespace-pre-wrap">
                              {message.content}
                            </p>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 text-right">
                          {message.timestamp.toLocaleTimeString()}
                        </p>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
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
        <div
          className={`p-4 border-t border-slate-200 dark:border-slate-800 ${
            isDraggingAttachment
              ? 'bg-sky-50 dark:bg-sky-950/20'
              : 'bg-transparent'
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            className="hidden"
            onChange={handleFileInputChange}
          />
          {attachments.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
              {attachments.map((attachment, idx) => (
                <div
                  key={`${attachment.name || 'image'}-${idx}`}
                  className="relative"
                >
                  <ImagePreview
                    src={`data:${attachment.mime_type};base64,${attachment.data}`}
                    alt={attachment.name || `Attachment ${idx + 1}`}
                    className="h-16 w-16 border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800"
                    thumbnailClassName="h-full w-full object-cover"
                    maxHeight="64px"
                  />
                  <button
                    type="button"
                    onClick={() => removeAttachment(idx)}
                    className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-slate-950/70 text-white hover:bg-slate-950 z-10"
                    aria-label="移除图片"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-end gap-3">
            <Textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleInputKeyDown}
              onPaste={handlePaste}
              placeholder={
                !isConfigured
                  ? t.devicePanel.configureFirst
                  : t.devicePanel.whatToDo
              }
              disabled={loading}
              className="flex-1 min-h-[40px] max-h-[120px] resize-none"
              rows={1}
            />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  disabled={
                    loading || attachments.length >= MAX_IMAGE_ATTACHMENTS
                  }
                  className="h-10 w-10 flex-shrink-0"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <ImagePlus className="w-4 h-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top" sideOffset={8}>
                添加图片
              </TooltipContent>
            </Tooltip>
            {/* Workflow Quick Run Button */}
            <Tooltip>
              <TooltipTrigger asChild>
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
                            <a
                              href="/workflows"
                              className="text-primary underline"
                            >
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
              </TooltipTrigger>
              <TooltipContent side="top" sideOffset={8} className="max-w-xs">
                <div className="space-y-1">
                  <p className="font-medium">
                    {t.devicePanel.tooltips.workflowButton}
                  </p>
                  <p className="text-xs opacity-80">
                    {t.devicePanel.tooltips.workflowButtonDesc}
                  </p>
                </div>
              </TooltipContent>
            </Tooltip>
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
                disabled={
                  (!input.trim() && attachments.length === 0) || !sessionReady
                }
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

      <DeviceMonitor
        deviceId={deviceId}
        serial={deviceSerial}
        connectionType={deviceConnectionType}
        isVisible={isVisible} // ✅ 修改：传递实际的 isVisible（原为硬编码 true）
      />
    </div>
  );
}
