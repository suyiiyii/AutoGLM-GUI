import * as React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useTranslation } from '../lib/i18n-context';
import { DeviceMonitor } from './DeviceMonitor';
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Send,
  RotateCcw,
  Layers,
  MessageSquare,
  Wrench,
  ChevronDown,
  ChevronUp,
  History,
  ListChecks,
  Square,
} from 'lucide-react';
import type { Workflow } from '../api';
import { listWorkflows, getErrorMessage } from '../api';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  createHistoryItem,
  saveHistoryItem,
  loadHistoryItems,
  clearHistory,
  deleteHistoryItem,
} from '../utils/history';
import type { HistoryItem } from '../types/history';
import { HistoryItemCard } from './HistoryItemCard';

interface ChatKitPanelProps {
  deviceId: string;
  deviceSerial: string; // Used for history storage
  deviceName: string;
  isVisible: boolean;
}

// 执行步骤类型
interface ExecutionStep {
  id: string;
  type: 'user' | 'thinking' | 'tool_call' | 'tool_result' | 'assistant';
  content: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  toolResult?: string;
  timestamp: Date;
  isExpanded?: boolean;
}

// 消息类型
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  steps?: ExecutionStep[];
  isStreaming?: boolean;
  success?: boolean;
}

export function ChatKitPanel({
  deviceId,
  deviceSerial,
  deviceName,
  isVisible,
}: ChatKitPanelProps) {
  const t = useTranslation();

  // Chat state
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [input, setInput] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [aborting, setAborting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const messagesEndRef = React.useRef<HTMLDivElement>(null);
  const eventSourceRef = React.useRef<EventSource | null>(null);
  const abortControllerRef = React.useRef<AbortController | null>(null);

  // Workflow state
  const [workflows, setWorkflows] = React.useState<Workflow[]>([]);
  const [showWorkflowPopover, setShowWorkflowPopover] = React.useState(false);

  // History state
  const [historyItems, setHistoryItems] = React.useState<HistoryItem[]>([]);
  const [showHistoryPopover, setShowHistoryPopover] = React.useState(false);

  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  React.useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Load workflows
  React.useEffect(() => {
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

  // Load history items when popover opens
  React.useEffect(() => {
    if (showHistoryPopover) {
      const items = loadHistoryItems(deviceSerial);
      setHistoryItems(items);
    }
  }, [showHistoryPopover, deviceSerial]);

  const handleExecuteWorkflow = (workflow: Workflow) => {
    setInput(workflow.text);
    setShowWorkflowPopover(false);
  };

  const handleSelectHistory = (item: HistoryItem) => {
    const userMessage: Message = {
      id: `${item.id}-user`,
      role: 'user',
      content: item.taskText,
      timestamp: item.startTime,
    };
    const agentMessage: Message = {
      id: `${item.id}-agent`,
      role: 'assistant',
      content: item.finalMessage,
      timestamp: item.endTime,
      steps: [],
      success: item.success,
      isStreaming: false,
    };
    setMessages([userMessage, agentMessage]);
    setShowHistoryPopover(false);
  };

  const handleClearHistory = () => {
    if (confirm(t.history?.clearAllConfirm || 'Clear all history?')) {
      clearHistory(deviceSerial);
      setHistoryItems([]);
    }
  };

  const handleDeleteHistoryItem = (itemId: string) => {
    deleteHistoryItem(deviceSerial, itemId);
    setHistoryItems(prev => prev.filter(item => item.id !== itemId));
  };

  // Toggle step expansion
  const toggleStepExpansion = (messageId: string, stepId: string) => {
    setMessages(prev =>
      prev.map(msg =>
        msg.id === messageId
          ? {
              ...msg,
              steps: msg.steps?.map(step =>
                step.id === stepId
                  ? { ...step, isExpanded: !step.isExpanded }
                  : step
              ),
            }
          : msg
      )
    );
  };

  // Send message using Layered Agent API
  const handleSend = React.useCallback(async () => {
    const inputValue = input.trim();
    if (!inputValue || loading) return;

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

    const agentMessageId = (Date.now() + 1).toString();
    const agentMessage: Message = {
      id: agentMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      steps: [],
      isStreaming: true,
    };

    setMessages(prev => [...prev, agentMessage]);

    // Create abort controller for this request
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      // Use simplified layered agent API
      const response = await fetch('/api/layered-agent/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: inputValue,
          device_id: deviceId,
          session_id: deviceId, // 使用 deviceId 作为 session 标识，保持对话上下文
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        let errorDetail = `HTTP error! status: ${response.status}`;
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            errorDetail = errorData.detail;
          }
        } catch {
          // 如果无法解析响应体，使用默认的状态码错误
        }
        throw new Error(errorDetail);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';
      const steps: ExecutionStep[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              // Handle different event types from layered agent API
              if (data.type === 'tool_call') {
                // Tool call step
                const step: ExecutionStep = {
                  id: `step-${Date.now()}-${Math.random()}`,
                  type: 'tool_call',
                  content:
                    data.tool_name === 'chat'
                      ? `发送指令给 Phone Agent`
                      : data.tool_name === 'list_devices'
                        ? '获取设备列表'
                        : `调用工具: ${data.tool_name}`,
                  toolName: data.tool_name,
                  toolArgs: data.tool_args || {},
                  timestamp: new Date(),
                  isExpanded: true,
                };
                steps.push(step);
                setMessages(prev =>
                  prev.map(msg =>
                    msg.id === agentMessageId
                      ? { ...msg, steps: [...steps] }
                      : msg
                  )
                );
              } else if (data.type === 'tool_result') {
                // Tool result
                const step: ExecutionStep = {
                  id: `step-${Date.now()}-${Math.random()}`,
                  type: 'tool_result',
                  content:
                    data.tool_name === 'chat'
                      ? 'Phone Agent 执行结果'
                      : `${data.tool_name} 结果`,
                  toolResult: data.result,
                  timestamp: new Date(),
                  isExpanded: true,
                };
                steps.push(step);
                setMessages(prev =>
                  prev.map(msg =>
                    msg.id === agentMessageId
                      ? { ...msg, steps: [...steps] }
                      : msg
                  )
                );
              } else if (data.type === 'message') {
                // Intermediate message
                setMessages(prev =>
                  prev.map(msg =>
                    msg.id === agentMessageId
                      ? { ...msg, content: data.content }
                      : msg
                  )
                );
              } else if (data.type === 'done') {
                // Final response
                const updatedAgentMessage = {
                  ...agentMessage,
                  content: data.content || '',
                  isStreaming: false,
                  success: data.success,
                  steps: [...steps],
                  timestamp: new Date(),
                };
                setMessages(prev =>
                  prev.map(msg =>
                    msg.id === agentMessageId ? updatedAgentMessage : msg
                  )
                );
                // Save to history
                const historyItem = createHistoryItem(
                  deviceSerial,
                  deviceName,
                  userMessage,
                  {
                    content: data.content || '',
                    timestamp: new Date(),
                    success: data.success,
                    steps: steps.length,
                  }
                );
                saveHistoryItem(deviceSerial, historyItem);
              } else if (data.type === 'error') {
                // Error
                const updatedAgentMessage = {
                  ...agentMessage,
                  content: `错误: ${data.message}`,
                  isStreaming: false,
                  success: false,
                  steps: [...steps],
                  timestamp: new Date(),
                };
                setMessages(prev =>
                  prev.map(msg =>
                    msg.id === agentMessageId ? updatedAgentMessage : msg
                  )
                );
                setError(data.message);
                // Save failed task to history
                const historyItem = createHistoryItem(
                  deviceSerial,
                  deviceName,
                  userMessage,
                  {
                    content: `错误: ${data.message}`,
                    timestamp: new Date(),
                    success: false,
                    steps: steps.length,
                  }
                );
                saveHistoryItem(deviceSerial, historyItem);
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e, line);
            }
          }
        }
      }

      // Mark as complete if not already
      setMessages(prev =>
        prev.map(msg =>
          msg.id === agentMessageId && msg.isStreaming
            ? { ...msg, isStreaming: false, success: true }
            : msg
        )
      );
    } catch (err) {
      // Handle abort error silently (user initiated)
      if (err instanceof Error && err.name === 'AbortError') {
        console.log('Chat aborted by user');
        return;
      }

      console.error('Chat error:', err);
      const errorMessage = getErrorMessage(err);
      setError(errorMessage);
      setMessages(prev =>
        prev.map(msg =>
          msg.id === agentMessageId
            ? {
                ...msg,
                content: `错误: ${errorMessage}`,
                isStreaming: false,
                success: false,
              }
            : msg
        )
      );
      // Save failed task to history
      const historyItem = createHistoryItem(
        deviceSerial,
        deviceName,
        userMessage,
        {
          content: `错误: ${errorMessage}`,
          timestamp: new Date(),
          success: false,
          steps: 0,
        }
      );
      saveHistoryItem(deviceSerial, historyItem);
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  }, [input, loading, deviceId, deviceSerial, deviceName]);

  // Abort chat function
  const handleAbort = React.useCallback(() => {
    if (!abortControllerRef.current) return;

    setAborting(true);

    try {
      // Abort the fetch request
      abortControllerRef.current.abort();
      abortControllerRef.current = null;

      // Update UI - set isStreaming to false
      setMessages(prev => {
        const lastMessage = prev[prev.length - 1];
        if (
          lastMessage &&
          lastMessage.role === 'assistant' &&
          lastMessage.isStreaming
        ) {
          return prev.map((msg, index) =>
            index === prev.length - 1
              ? {
                  ...msg,
                  content: msg.content || t.chat?.aborted || '任务已中断',
                  isStreaming: false,
                  success: false,
                }
              : msg
          );
        }
        return prev;
      });

      // Notify backend to abort (don't wait for response)
      // Use deviceId as session_id (same as in handleSend)
      import('../api').then(({ abortLayeredAgentChat }) => {
        abortLayeredAgentChat(deviceId).catch(e =>
          console.error('Backend abort failed:', e)
        );
      });
    } catch (error) {
      console.error('Failed to abort chat:', error);
    } finally {
      setLoading(false);
      setAborting(false);
    }
  }, [t, deviceId]);

  const handleReset = React.useCallback(async () => {
    // Abort any ongoing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setMessages([]);
    setError(null);
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    // 清除后端的对话历史 session
    try {
      await fetch('/api/layered-agent/reset', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: deviceId,
        }),
      });
    } catch (e) {
      // 忽略 reset 失败，不影响用户体验
      console.warn('Failed to reset backend session:', e);
    }
  }, [deviceId]);

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
      {/* Chat Area with Execution Steps */}
      <Card className="flex-1 flex flex-col min-h-0 max-w-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-purple-500/10">
              <Layers className="h-5 w-5 text-purple-500" />
            </div>
            <div>
              <h2 className="font-bold text-slate-900 dark:text-slate-100">
                {t.chatkit?.title || 'AI Agent'}
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {deviceName} • {t.chatkit?.layeredAgent || '分层代理模式'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant="secondary"
              className="bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300"
            >
              {t.chatkit?.layeredAgent || '分层代理模式'}
            </Badge>
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
                  title={t.history?.title || 'History'}
                >
                  <History className="h-4 w-4" />
                </Button>
              </PopoverTrigger>

              <PopoverContent className="w-96 p-0" align="end" sideOffset={8}>
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800">
                  <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                    {t.history?.title || 'History'}
                  </h3>
                  {historyItems.length > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleClearHistory}
                      className="h-7 text-xs"
                    >
                      {t.history?.clearAll || 'Clear All'}
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
                          onDelete={handleDeleteHistoryItem}
                        />
                      ))
                    ) : (
                      <div className="text-center py-8">
                        <History className="h-12 w-12 text-slate-300 dark:text-slate-700 mx-auto mb-3" />
                        <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                          {t.history?.noHistory || 'No history yet'}
                        </p>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                          {t.history?.noHistoryDescription ||
                            'Your completed tasks will appear here'}
                        </p>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </PopoverContent>
            </Popover>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleReset}
              className="h-8 w-8 rounded-full"
              title="重置对话"
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

        {/* Messages with Execution Steps */}
        <ScrollArea className="flex-1 min-h-0">
          <div className="p-4 space-y-4">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center py-12">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-purple-100 dark:bg-purple-900/30 mb-4">
                  <Layers className="h-8 w-8 text-purple-500" />
                </div>
                <p className="font-medium text-slate-900 dark:text-slate-100">
                  {t.chatkit?.title || '分层代理模式'}
                </p>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400 max-w-xs">
                  {t.chatkit?.layeredAgentDesc ||
                    '决策模型负责规划任务，视觉模型负责执行。你可以看到每一步的执行过程。'}
                </p>
              </div>
            ) : (
              messages.map(message => (
                <div key={message.id} className="space-y-2">
                  {message.role === 'user' ? (
                    <div className="flex justify-end">
                      <div className="max-w-[80%]">
                        <div className="bg-purple-600 text-white px-4 py-2 rounded-2xl rounded-br-sm">
                          <p className="whitespace-pre-wrap">
                            {message.content}
                          </p>
                        </div>
                        <p className="text-xs text-slate-400 mt-1 text-right">
                          {message.timestamp.toLocaleTimeString()}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {/* Execution Steps */}
                      {message.steps && message.steps.length > 0 && (
                        <div className="space-y-2">
                          {message.steps.map((step, idx) => (
                            <div
                              key={step.id}
                              className="bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden"
                            >
                              {/* Step Header */}
                              <button
                                onClick={() =>
                                  toggleStepExpansion(message.id, step.id)
                                }
                                className="w-full flex items-center justify-between p-3 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                              >
                                <div className="flex items-center gap-2">
                                  <div
                                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${
                                      step.type === 'tool_call'
                                        ? 'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400'
                                        : 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400'
                                    }`}
                                  >
                                    {step.type === 'tool_call' ? (
                                      <Wrench className="w-3 h-3" />
                                    ) : (
                                      <MessageSquare className="w-3 h-3" />
                                    )}
                                  </div>
                                  <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                    Step {idx + 1}: {step.content}
                                  </span>
                                </div>
                                {step.isExpanded ? (
                                  <ChevronUp className="w-4 h-4 text-slate-400" />
                                ) : (
                                  <ChevronDown className="w-4 h-4 text-slate-400" />
                                )}
                              </button>

                              {/* Step Content */}
                              {step.isExpanded && (
                                <div className="px-3 pb-3 space-y-2">
                                  {step.type === 'tool_call' &&
                                    step.toolArgs && (
                                      <div className="bg-white dark:bg-slate-900 rounded-lg p-3 text-sm">
                                        <p className="text-xs text-slate-500 mb-1 font-medium">
                                          {step.toolName === 'chat'
                                            ? '发送给 Phone Agent 的指令:'
                                            : '工具参数:'}
                                        </p>
                                        {step.toolName === 'chat' ? (
                                          <p className="text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                                            {(
                                              step.toolArgs as {
                                                message?: string;
                                              }
                                            ).message ||
                                              JSON.stringify(
                                                step.toolArgs,
                                                null,
                                                2
                                              )}
                                          </p>
                                        ) : (
                                          <pre className="text-xs text-slate-600 dark:text-slate-400 overflow-x-auto">
                                            {JSON.stringify(
                                              step.toolArgs,
                                              null,
                                              2
                                            )}
                                          </pre>
                                        )}
                                      </div>
                                    )}
                                  {step.type === 'tool_result' &&
                                    step.toolResult && (
                                      <div className="bg-white dark:bg-slate-900 rounded-lg p-3 text-sm">
                                        <p className="text-xs text-slate-500 mb-1 font-medium">
                                          执行结果:
                                        </p>
                                        <pre className="text-xs text-slate-600 dark:text-slate-400 overflow-x-auto whitespace-pre-wrap">
                                          {typeof step.toolResult === 'string'
                                            ? step.toolResult
                                            : JSON.stringify(
                                                step.toolResult,
                                                null,
                                                2
                                              )}
                                        </pre>
                                      </div>
                                    )}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Final Response */}
                      {message.content && (
                        <div className="flex justify-start">
                          <div
                            className={`max-w-[85%] rounded-2xl rounded-tl-sm px-4 py-3 ${
                              message.success === false
                                ? 'bg-red-100 dark:bg-red-900/20 text-red-600 dark:text-red-400'
                                : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                            }`}
                          >
                            <div className="flex items-start gap-2">
                              {message.success !== undefined && (
                                <CheckCircle2
                                  className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                                    message.success
                                      ? 'text-green-500'
                                      : 'text-red-500'
                                  }`}
                                />
                              )}
                              <p className="whitespace-pre-wrap">
                                {message.content}
                              </p>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Streaming indicator */}
                      {message.isStreaming && !message.content && (
                        <div className="flex items-center gap-2 text-sm text-slate-500">
                          <Loader2 className="w-4 h-4 animate-spin" />
                          正在思考和执行...
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Input area */}
        <div className="p-4 border-t border-slate-200 dark:border-slate-800">
          <div className="flex items-end gap-3">
            <Textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder="描述你想要完成的任务... (Cmd+Enter 发送)"
              disabled={loading}
              className="flex-1 min-h-[40px] max-h-[120px] resize-none"
              rows={1}
            />
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
                        {t.workflows?.selectWorkflow || 'Select Workflow'}
                      </h4>
                      {workflows.length === 0 ? (
                        <div className="text-sm text-slate-500 dark:text-slate-400 space-y-1">
                          <p>{t.workflows?.empty || 'No workflows yet'}</p>
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
                    {t.devicePanel?.tooltips?.workflowButton ||
                      'Quick Workflow'}
                  </p>
                  <p className="text-xs opacity-80">
                    {t.devicePanel?.tooltips?.workflowButtonDesc ||
                      'Select a workflow to quickly fill in the task'}
                  </p>
                </div>
              </TooltipContent>
            </Tooltip>
            {/* Abort Button - shown when loading */}
            {loading && (
              <Button
                onClick={handleAbort}
                disabled={aborting}
                size="icon"
                variant="destructive"
                className="h-10 w-10 rounded-full flex-shrink-0"
                title={t.chat?.abortChat || '中断任务'}
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
                className="h-10 w-10 rounded-full flex-shrink-0 bg-purple-600 hover:bg-purple-700"
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </Card>

      <DeviceMonitor deviceId={deviceId} isVisible={isVisible} />
    </div>
  );
}
