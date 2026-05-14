import React, { useRef, useCallback, useState, useEffect } from 'react';
import {
  Send,
  RotateCcw,
  History,
  Loader2,
  Square,
  ImagePlus,
  X,
  Sparkles,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import type { TaskImageAttachment, HistoryRecordResponse } from '../api';
import {
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
  useChatAgentConversation,
  type ChatConversationMessage,
} from '../hooks/useChatAgentConversation';

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

export function ChatAgentPanel() {
  const t = useTranslation();
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<TaskImageAttachment[]>([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [isDraggingAttachment, setIsDraggingAttachment] = useState(false);
  const [expandedThinkings, setExpandedThinkings] = useState<Set<string>>(
    new Set()
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showHistoryPopover, setShowHistoryPopover] = useState(false);
  const [historyItems, setHistoryItems] = useState<HistoryRecordResponse[]>([]);
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
  } = useChatAgentConversation();
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef(0);
  const prevMessageSigRef = useRef<string | null>(null);
  const isAtBottomRef = useRef(true);
  const lastPinTimeRef = useRef(0);
  const lastScrollTopRef = useRef(0);
  const [showNewMessageNotice, setShowNewMessageNotice] = useState(false);

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

  // Load history items when popover opens
  useEffect(() => {
    if (showHistoryPopover) {
      const loadItems = async () => {
        try {
          const data = await listHistory('chat', 20, 0, 'chat');
          setHistoryItems(data.records);
        } catch (err) {
          console.error('Failed to load chat history:', err);
          setHistoryItems([]);
        }
      };
      loadItems();
    }
  }, [showHistoryPopover]);

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

  const handleMessagesScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const scrollTop = target.scrollTop;
    const prevScrollTop = lastScrollTopRef.current;
    lastScrollTopRef.current = scrollTop;

    if (performance.now() - lastPinTimeRef.current < 150) return;

    const distanceFromBottom =
      target.scrollHeight - scrollTop - target.clientHeight;
    if (distanceFromBottom < 150) {
      isAtBottomRef.current = true;
      setShowNewMessageNotice(false);
      return;
    }
    if (scrollTop < prevScrollTop - 4) {
      isAtBottomRef.current = false;
    }
  };

  const handleScrollToLatest = () => {
    isAtBottomRef.current = true;
    pinToBottom();
    setShowNewMessageNotice(false);
  };

  const handleSelectHistory = (record: HistoryRecordResponse) => {
    void (async () => {
      let selectedRecord = record;
      try {
        selectedRecord = await getHistoryRecord('chat', record.id);
      } catch (err) {
        console.error('Failed to load history record detail:', err);
      }

      // 将历史记录的所有 messages 转换为聊天消息
      const newMessages: ChatConversationMessage[] = [];
      let msgIndex = 0;
      for (const msg of selectedRecord.messages) {
        if (msg.role === 'user') {
          newMessages.push({
            id: `${selectedRecord.id}-user-${msgIndex}`,
            role: 'user',
            content: msg.content || selectedRecord.task_text,
            timestamp: new Date(msg.timestamp),
            attachments: msg.attachments || [],
          });
        } else if (msg.role === 'assistant') {
          newMessages.push({
            id: `${selectedRecord.id}-agent-${msgIndex}`,
            role: 'assistant',
            content: msg.content || '',
            timestamp: new Date(msg.timestamp),
            steps: msg.step ?? undefined,
            success: selectedRecord.success,
            isStreaming: false,
            thinking: msg.thinking ? [msg.thinking] : undefined,
          });
        }
        msgIndex++;
      }

      // 如果没有 messages，fallback 到旧的单轮逻辑
      if (newMessages.length === 0) {
        newMessages.push({
          id: `${selectedRecord.id}-user`,
          role: 'user',
          content: selectedRecord.task_text,
          timestamp: new Date(selectedRecord.start_time),
        });
        newMessages.push({
          id: `${selectedRecord.id}-agent`,
          role: 'assistant',
          content: selectedRecord.final_message,
          timestamp: selectedRecord.end_time
            ? new Date(selectedRecord.end_time)
            : new Date(selectedRecord.start_time),
          steps: selectedRecord.steps,
          success: selectedRecord.success,
          isStreaming: false,
        });
      }

      setMessages(newMessages);
      setShowHistoryPopover(false);
    })();
  };

  const handleClearHistory = async () => {
    if (confirm(t.history.clearAllConfirm)) {
      try {
        await clearHistoryApi('chat');
        setHistoryItems([]);
      } catch (err) {
        console.error('Failed to clear history:', err);
      }
    }
  };

  const handleDeleteItem = async (itemId: string) => {
    try {
      await deleteHistoryRecord('chat', itemId);
      setHistoryItems(prev => prev.filter(item => item.id !== itemId));
    } catch (err) {
      console.error('Failed to delete history item:', err);
    }
  };

  const handleReset = useCallback(async () => {
    await resetConversation();
    setShowNewMessageNotice(false);
    isAtBottomRef.current = true;
    prevMessageCountRef.current = 0;
    prevMessageSigRef.current = null;
    setAttachments([]);
    setAttachmentError(null);
  }, [resetConversation]);

  const addImageFiles = useCallback(
    async (files: File[]) => {
      const imageFiles = files.filter(file =>
        IMAGE_ATTACHMENT_TYPES.has(file.type)
      );
      if (imageFiles.length === 0) return;

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
      if (!hasImages) return;
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
      if (!hasImages) return;
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
  }, [input, attachments, sendMessage]);

  const handleInputKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        void handleSend();
      }
    },
    [handleSend]
  );

  return (
    <Card className="flex-1 flex flex-col min-h-0 max-w-3xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-600/10">
            <Sparkles className="h-5 w-5 text-emerald-600" />
          </div>
          <div>
            <div className="flex items-center gap-1">
              <h2 className="font-bold text-slate-900 dark:text-slate-100">
                {t.chatkit.chatMode}
              </h2>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 font-mono">
              chat
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* History popover */}
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
              <ScrollArea className="h-[400px]">
                <div className="p-4 space-y-2">
                  {historyItems.length > 0 ? (
                    historyItems.map(item => (
                      <HistoryItemCard
                        key={item.id}
                        item={item}
                        onSelect={() => handleSelectHistory(item)}
                        onDelete={() => handleDeleteItem(item.id)}
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

          {!sessionReady && (
            <Badge variant="outline" className="text-xs">
              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
              初始化中
            </Badge>
          )}

          <Button
            variant="ghost"
            size="icon"
            onClick={() => void handleReset()}
            disabled={loading}
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
          onScroll={handleMessagesScroll}
        >
          <div className="p-4" ref={contentRef}>
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center min-h-[calc(100%-1rem)]">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-600/10 mb-4">
                  <Sparkles className="h-8 w-8 text-emerald-600" />
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
                    <div className="max-w-[85%] space-y-3 min-w-0">
                      {/* Completed thinking blocks — collapsible */}
                      {message.thinking &&
                        message.thinking.length > 0 &&
                        message.thinking.map((thinking, idx) => {
                          const key = `${message.id}-thinking-${idx}`;
                          const isExpanded = expandedThinkings.has(key);
                          return (
                            <div
                              key={idx}
                              className="bg-slate-50 dark:bg-slate-900/50 rounded-2xl rounded-tl-sm px-4 py-2 border border-slate-200 dark:border-slate-700 min-w-0"
                            >
                              <button
                                type="button"
                                onClick={() =>
                                  setExpandedThinkings(prev => {
                                    const next = new Set(prev);
                                    if (next.has(key)) {
                                      next.delete(key);
                                    } else {
                                      next.add(key);
                                    }
                                    return next;
                                  })
                                }
                                className="flex items-center gap-2 w-full text-left"
                              >
                                {isExpanded ? (
                                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                                ) : (
                                  <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                                )}
                                <span className="text-xs font-medium text-slate-400 dark:text-slate-500">
                                  深度思考
                                </span>
                              </button>
                              {isExpanded && (
                                <p className="mt-2 text-sm whitespace-pre-wrap text-slate-500 dark:text-slate-400 break-all overflow-hidden min-w-0">
                                  {thinking}
                                </p>
                              )}
                            </div>
                          );
                        })}

                      {/* Current thinking being streamed — always expanded */}
                      {message.currentThinking && (
                        <div className="bg-slate-50 dark:bg-slate-900/50 rounded-2xl rounded-tl-sm px-4 py-3 border border-slate-200 dark:border-slate-700 min-w-0">
                          <div className="flex items-center gap-2 mb-2">
                            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600/10">
                              <Sparkles className="h-3 w-3 text-emerald-600 animate-pulse" />
                            </div>
                            <span className="text-xs font-medium text-slate-400 dark:text-slate-500">
                              深度思考中...
                            </span>
                          </div>
                          <p className="text-sm whitespace-pre-wrap text-slate-500 dark:text-slate-400 break-all overflow-hidden min-w-0">
                            {message.currentThinking}
                            <span className="inline-block w-1 h-4 ml-0.5 bg-emerald-600 animate-pulse" />
                          </p>
                        </div>
                      )}

                      {/* Streaming content */}
                      {message.currentContent && (
                        <div className="bg-slate-100 dark:bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-3 min-w-0">
                          <p className="text-sm whitespace-pre-wrap text-slate-700 dark:text-slate-300 break-all overflow-hidden min-w-0">
                            {message.currentContent}
                            <span className="inline-block w-1.5 h-4 ml-0.5 bg-emerald-600 animate-pulse" />
                          </p>
                        </div>
                      )}

                      {/* Final content */}
                      {message.content && !message.currentContent && (
                        <div
                          className={`
                            rounded-2xl px-4 py-3 flex items-start gap-2 min-w-0
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
                          <div className="min-w-0">
                            <p className="whitespace-pre-wrap break-all overflow-hidden min-w-0">
                              {message.content}
                            </p>
                          </div>
                        </div>
                      )}

                      {/* Streaming indicator (no content yet) */}
                      {message.isStreaming &&
                        !message.currentThinking &&
                        !message.currentContent && (
                          <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            Processing...
                          </div>
                        )}
                    </div>
                  ) : (
                    <div className="max-w-[75%] min-w-0">
                      <div className="chat-bubble-user px-4 py-3 space-y-2 min-w-0">
                        {message.attachments &&
                          message.attachments.length > 0 && (
                            <div className="grid grid-cols-2 gap-2">
                              {message.attachments.map((attachment, idx) => (
                                <img
                                  key={`${message.id}-attachment-${idx}`}
                                  src={`data:${attachment.mime_type};base64,${attachment.data}`}
                                  alt={
                                    attachment.name || `Attachment ${idx + 1}`
                                  }
                                  className="h-24 w-full rounded-lg object-cover border border-white/20"
                                />
                              ))}
                            </div>
                          )}
                        {message.content && (
                          <p className="whitespace-pre-wrap break-all overflow-hidden min-w-0">
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
              className="pointer-events-auto shadow-lg bg-emerald-600 text-white hover:bg-emerald-700"
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
                className="relative h-16 w-16 overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800"
              >
                <img
                  src={`data:${attachment.mime_type};base64,${attachment.data}`}
                  alt={attachment.name || `Attachment ${idx + 1}`}
                  className="h-full w-full object-cover"
                />
                <button
                  type="button"
                  onClick={() => removeAttachment(idx)}
                  className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-slate-950/70 text-white hover:bg-slate-950"
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
              !sessionReady
                ? t.devicePanel.configureFirst
                : t.devicePanel.whatToDo
            }
            disabled={loading}
            className="flex-1 min-h-[40px] max-h-[120px] resize-none"
            rows={1}
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            disabled={loading || attachments.length >= MAX_IMAGE_ATTACHMENTS}
            className="h-10 w-10 flex-shrink-0"
            onClick={() => fileInputRef.current?.click()}
          >
            <ImagePlus className="w-4 h-4" />
          </Button>
          {/* Abort Button - shown when loading */}
          {loading && (
            <Button
              onClick={() => void abortConversation()}
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
              onClick={() => void handleSend()}
              disabled={
                (!input.trim() && attachments.length === 0) || !sessionReady
              }
              size="icon"
              className="h-10 w-10 rounded-full flex-shrink-0 bg-emerald-600 text-white hover:bg-emerald-700"
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
