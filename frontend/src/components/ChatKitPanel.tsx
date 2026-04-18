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
  Send,
  RotateCcw,
  Layers,
  MessageSquare,
  Wrench,
  ChevronDown,
  ChevronUp,
  History,
  ListChecks,
  Loader2,
  Square,
} from 'lucide-react';
import type { Workflow, HistoryRecordResponse } from '../api';
import {
  cancelTaskRun,
  createTaskSession,
  getTaskSession,
  listWorkflows,
  getErrorMessage,
  listHistory,
  clearHistory as clearHistoryApi,
  deleteHistoryRecord,
  listTaskEvents,
  listTaskSessionTasks,
  resetTaskSession,
  streamTaskEvents,
  submitTaskSessionTask,
  type TaskEventRecordResponse,
  type TaskRunResponse,
  type TaskStatus,
} from '../api';
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
import { HistoryItemCard } from './HistoryItemCard';

interface ChatKitPanelProps {
  deviceId: string;
  deviceSerial: string; // Used for history storage
  deviceName: string;
  deviceConnectionType?: string;
  isVisible: boolean;
  unlimitedStepsEnabled?: boolean;
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

function isTaskActive(status: TaskStatus): boolean {
  return status === 'QUEUED' || status === 'RUNNING';
}

function applyTaskEventToTask(
  task: TaskRunResponse,
  event: TaskEventRecordResponse
): TaskRunResponse {
  const nextTask = { ...task };
  const payload = event.payload;

  if (event.event_type === 'status') {
    if (typeof payload.status === 'string') {
      nextTask.status = payload.status as TaskStatus;
      if (!isTaskActive(nextTask.status) && !nextTask.finished_at) {
        nextTask.finished_at = event.created_at;
      }
    }
  } else if (event.event_type === 'done') {
    nextTask.status = 'SUCCEEDED';
    nextTask.final_message =
      typeof payload.content === 'string'
        ? payload.content
        : typeof payload.message === 'string'
          ? payload.message
          : null;
    nextTask.error_message = null;
    nextTask.finished_at = event.created_at;
  } else if (event.event_type === 'error') {
    nextTask.status = 'FAILED';
    nextTask.final_message =
      typeof payload.message === 'string' ? payload.message : null;
    nextTask.error_message =
      typeof payload.message === 'string' ? payload.message : null;
    nextTask.finished_at = event.created_at;
  } else if (event.event_type === 'cancelled') {
    nextTask.status = 'CANCELLED';
    nextTask.final_message =
      typeof payload.message === 'string' ? payload.message : null;
    nextTask.error_message =
      typeof payload.message === 'string' ? payload.message : null;
    nextTask.finished_at = event.created_at;
  }

  return nextTask;
}

function reconcileTaskRun(
  task: TaskRunResponse,
  events: TaskEventRecordResponse[]
): TaskRunResponse {
  return events.reduce(
    (currentTask, event) => applyTaskEventToTask(currentTask, event),
    { ...task }
  );
}

function buildExecutionSteps(
  events: TaskEventRecordResponse[]
): ExecutionStep[] {
  const steps: ExecutionStep[] = [];

  events.forEach(event => {
    const payload = event.payload;

    if (event.event_type === 'tool_call') {
      const toolName =
        typeof payload.tool_name === 'string' ? payload.tool_name : 'unknown';
      steps.push({
        id: `step-${event.task_id}-${event.seq}`,
        type: 'tool_call',
        content:
          toolName === 'chat'
            ? '发送指令给 Phone Agent'
            : toolName === 'list_devices'
              ? '获取设备列表'
              : `调用工具: ${toolName}`,
        toolName,
        toolArgs:
          (payload.tool_args as Record<string, unknown> | undefined) || {},
        timestamp: new Date(event.created_at),
        isExpanded: true,
      });
    } else if (event.event_type === 'tool_result') {
      const toolName =
        typeof payload.tool_name === 'string' ? payload.tool_name : 'unknown';
      steps.push({
        id: `step-${event.task_id}-${event.seq}`,
        type: 'tool_result',
        content:
          toolName === 'chat' ? 'Phone Agent 执行结果' : `${toolName} 结果`,
        toolName,
        toolResult:
          typeof payload.result === 'string'
            ? payload.result
            : JSON.stringify(payload.result ?? '', null, 2),
        timestamp: new Date(event.created_at),
        isExpanded: true,
      });
    }
  });

  return steps;
}

function buildAssistantMessage(
  task: TaskRunResponse,
  events: TaskEventRecordResponse[]
): Message {
  const steps = buildExecutionSteps(events);
  let content = task.final_message || task.error_message || '';

  for (const event of events) {
    const payload = event.payload;
    if (event.event_type === 'message' && typeof payload.content === 'string') {
      content = payload.content;
    } else if (event.event_type === 'done') {
      if (typeof payload.content === 'string') {
        content = payload.content;
      } else if (typeof payload.message === 'string') {
        content = payload.message;
      }
    } else if (
      (event.event_type === 'error' || event.event_type === 'cancelled') &&
      typeof payload.message === 'string'
    ) {
      content = payload.message;
    }
  }

  return {
    id: `${task.id}-agent`,
    role: 'assistant',
    content,
    timestamp: new Date(task.finished_at || task.started_at || task.created_at),
    steps,
    isStreaming: isTaskActive(task.status),
    success:
      task.status === 'SUCCEEDED'
        ? true
        : task.status === 'FAILED' ||
            task.status === 'CANCELLED' ||
            task.status === 'INTERRUPTED'
          ? false
          : undefined,
  };
}

function buildMessagePair(
  task: TaskRunResponse,
  events: TaskEventRecordResponse[]
): Message[] {
  return [
    {
      id: `${task.id}-user`,
      role: 'user',
      content: task.input_text,
      timestamp: new Date(task.created_at),
    },
    buildAssistantMessage(task, events),
  ];
}

export function ChatKitPanel({
  deviceId,
  deviceSerial,
  deviceName,
  deviceConnectionType,
  isVisible,
  unlimitedStepsEnabled = false,
}: ChatKitPanelProps) {
  const t = useTranslation();

  // Chat state
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [input, setInput] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [aborting, setAborting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const messagesEndRef = React.useRef<HTMLDivElement>(null);
  const scrollAreaRef = React.useRef<HTMLDivElement>(null);
  const [isNearBottom, setIsNearBottom] = React.useState(true);
  const taskStreamRef = React.useRef<{ close: () => void } | null>(null);
  const currentTaskIdRef = React.useRef<string | null>(null);
  const taskRunsRef = React.useRef<Record<string, TaskRunResponse>>({});
  const taskEventsRef = React.useRef<Record<string, TaskEventRecordResponse[]>>(
    {}
  );
  const sessionStorageKey = React.useMemo(
    () => `layered-task-session:${deviceId}`,
    [deviceId]
  );

  // Workflow state
  const [workflows, setWorkflows] = React.useState<Workflow[]>([]);
  const [showWorkflowPopover, setShowWorkflowPopover] = React.useState(false);

  // History state
  const [historyItems, setHistoryItems] = React.useState<
    HistoryRecordResponse[]
  >([]);
  const [showHistoryPopover, setShowHistoryPopover] = React.useState(false);

  // Handle scroll position tracking
  const handleScroll = React.useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      const target = event.currentTarget;
      const scrollHeight = target.scrollHeight;
      const scrollTop = target.scrollTop;
      const clientHeight = target.clientHeight;
      const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

      // Consider "near bottom" if within 200px
      setIsNearBottom(distanceFromBottom < 200);
    },
    []
  );

  // Auto-scroll to bottom only if user is near bottom
  React.useEffect(() => {
    if (isNearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isNearBottom]);

  React.useEffect(() => {
    return () => {
      if (taskStreamRef.current) {
        taskStreamRef.current.close();
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
      const loadItems = async () => {
        try {
          const data = await listHistory(deviceSerial, 20, 0);
          setHistoryItems(data.records);
        } catch (error) {
          console.error('Failed to load history:', error);
          setHistoryItems([]);
        }
      };
      loadItems();
    }
  }, [showHistoryPopover, deviceSerial]);

  const handleExecuteWorkflow = (workflow: Workflow) => {
    setInput(workflow.text);
    setShowWorkflowPopover(false);
  };

  const handleSelectHistory = (record: HistoryRecordResponse) => {
    const userMessage: Message = {
      id: `${record.id}-user`,
      role: 'user',
      content: record.task_text,
      timestamp: new Date(record.start_time),
    };
    const agentMessage: Message = {
      id: `${record.id}-agent`,
      role: 'assistant',
      content: record.final_message,
      timestamp: record.end_time
        ? new Date(record.end_time)
        : new Date(record.start_time),
      steps: [],
      success: record.success,
      isStreaming: false,
    };
    setMessages([userMessage, agentMessage]);
    setShowHistoryPopover(false);
  };

  const handleClearHistory = async () => {
    if (confirm(t.history?.clearAllConfirm || 'Clear all history?')) {
      try {
        await clearHistoryApi(deviceSerial);
        setHistoryItems([]);
      } catch (error) {
        console.error('Failed to clear history:', error);
      }
    }
  };

  const handleDeleteHistoryItem = async (itemId: string) => {
    try {
      await deleteHistoryRecord(deviceSerial, itemId);
      setHistoryItems(prev => prev.filter(item => item.id !== itemId));
    } catch (error) {
      console.error('Failed to delete history item:', error);
    }
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

  const replaceTaskMessages = React.useCallback(() => {
    const orderedTasks = Object.values(taskRunsRef.current).sort(
      (left, right) =>
        new Date(left.created_at).getTime() -
        new Date(right.created_at).getTime()
    );
    setMessages(
      orderedTasks.flatMap(task =>
        buildMessagePair(task, taskEventsRef.current[task.id] || [])
      )
    );
  }, []);

  const attachTaskStream = React.useCallback(
    (taskId: string, afterSeq: number = 0) => {
      if (taskStreamRef.current) {
        taskStreamRef.current.close();
      }

      taskStreamRef.current = streamTaskEvents(
        taskId,
        event => {
          const existingEvents = taskEventsRef.current[taskId] || [];
          taskEventsRef.current[taskId] = [...existingEvents, event];
          const task = taskRunsRef.current[taskId];
          if (task) {
            taskRunsRef.current[taskId] = applyTaskEventToTask(task, event);
          }
          replaceTaskMessages();

          const nextTask = taskRunsRef.current[taskId];
          if (nextTask && !isTaskActive(nextTask.status)) {
            currentTaskIdRef.current = null;
            setLoading(false);
            setAborting(false);
          }
        },
        message => {
          setError(message);
          setLoading(false);
          setAborting(false);
        },
        afterSeq
      );
    },
    [replaceTaskMessages]
  );

  const restoreSessionConversation = React.useCallback(
    async (nextSessionId: string) => {
      if (taskStreamRef.current) {
        taskStreamRef.current.close();
        taskStreamRef.current = null;
      }

      const { tasks } = await listTaskSessionTasks(nextSessionId);
      const orderedTasks = [...tasks].sort(
        (left, right) =>
          new Date(left.created_at).getTime() -
          new Date(right.created_at).getTime()
      );

      const reconciledTasks = await Promise.all(
        orderedTasks.map(async task => {
          const events = (await listTaskEvents(task.id)).events;
          taskEventsRef.current[task.id] = events;
          return reconcileTaskRun(task, events);
        })
      );

      taskRunsRef.current = Object.fromEntries(
        reconciledTasks.map(task => [task.id, task])
      );
      replaceTaskMessages();

      const activeTask = [...reconciledTasks]
        .reverse()
        .find(task => isTaskActive(task.status));
      if (activeTask) {
        currentTaskIdRef.current = activeTask.id;
        setLoading(true);
        const lastSeq =
          taskEventsRef.current[activeTask.id]?.[
            taskEventsRef.current[activeTask.id].length - 1
          ]?.seq || 0;
        attachTaskStream(activeTask.id, lastSeq);
      } else {
        currentTaskIdRef.current = null;
        setLoading(false);
      }
    },
    [attachTaskStream, replaceTaskMessages]
  );

  React.useEffect(() => {
    let disposed = false;

    const initializeSession = async () => {
      try {
        setError(null);
        const storedSessionId = sessionStorage.getItem(sessionStorageKey);
        let nextSessionId = storedSessionId;

        if (storedSessionId) {
          try {
            const existingSession = await getTaskSession(storedSessionId);
            if (
              existingSession.device_id !== deviceId ||
              existingSession.device_serial !== deviceSerial ||
              existingSession.mode !== 'layered' ||
              existingSession.status !== 'open'
            ) {
              nextSessionId = null;
            }
          } catch {
            nextSessionId = null;
          }
        }

        if (!nextSessionId) {
          const session = await createTaskSession(
            deviceId,
            deviceSerial,
            'layered'
          );
          nextSessionId = session.id;
          sessionStorage.setItem(sessionStorageKey, nextSessionId);
        }

        if (disposed || !nextSessionId) {
          return;
        }

        setSessionId(nextSessionId);
        await restoreSessionConversation(nextSessionId);
      } catch (sessionError) {
        if (!disposed) {
          console.error(
            'Failed to initialize layered task session:',
            sessionError
          );
          setError('Failed to restore layered chat session');
          setLoading(false);
        }
      }
    };

    void initializeSession();

    return () => {
      disposed = true;
      if (taskStreamRef.current) {
        taskStreamRef.current.close();
        taskStreamRef.current = null;
      }
    };
  }, [deviceId, deviceSerial, restoreSessionConversation, sessionStorageKey]);

  const handleSend = React.useCallback(async () => {
    const inputValue = input.trim();
    if (!inputValue || loading || !sessionId) return;

    setInput('');
    setLoading(true);
    setError(null);

    try {
      const task = await submitTaskSessionTask(sessionId, inputValue);
      const initialEvents = (await listTaskEvents(task.id)).events;
      const reconciledTask = reconcileTaskRun(task, initialEvents);
      taskRunsRef.current[task.id] = reconciledTask;
      taskEventsRef.current[task.id] = initialEvents;
      currentTaskIdRef.current = isTaskActive(reconciledTask.status)
        ? task.id
        : null;
      replaceTaskMessages();

      if (isTaskActive(reconciledTask.status)) {
        const lastSeq = initialEvents[initialEvents.length - 1]?.seq || 0;
        attachTaskStream(task.id, lastSeq);
      } else {
        setLoading(false);
        setAborting(false);
      }
    } catch (err) {
      console.error('Failed to submit layered task:', err);
      const errorMessage = getErrorMessage(err);
      setError(errorMessage);
    } finally {
      setLoading(false);
      setAborting(false);
    }
  }, [attachTaskStream, input, loading, replaceTaskMessages, sessionId]);

  const handleAbort = React.useCallback(() => {
    const taskId = currentTaskIdRef.current;
    if (!taskId) return;

    setAborting(true);

    void (async () => {
      try {
        const response = await cancelTaskRun(taskId);
        if (response.task) {
          taskRunsRef.current[taskId] = response.task;
          replaceTaskMessages();
        }
      } catch (abortError) {
        console.error('Failed to abort chat:', abortError);
        setError(getErrorMessage(abortError));
      }
    })().finally(() => {
      setLoading(false);
      setAborting(false);
    });
  }, [replaceTaskMessages]);

  const handleReset = React.useCallback(async () => {
    try {
      if (taskStreamRef.current) {
        taskStreamRef.current.close();
        taskStreamRef.current = null;
      }

      if (sessionId) {
        await resetTaskSession(sessionId);
      }

      const nextSession = await createTaskSession(
        deviceId,
        deviceSerial,
        'layered'
      );
      sessionStorage.setItem(sessionStorageKey, nextSession.id);
      setSessionId(nextSession.id);
      taskRunsRef.current = {};
      taskEventsRef.current = {};
      currentTaskIdRef.current = null;
      setMessages([]);
      setLoading(false);
      setError(null);
      setAborting(false);
    } catch (resetError) {
      console.error('Failed to reset layered task session:', resetError);
      setError(getErrorMessage(resetError));
    }
  }, [deviceId, deviceSerial, sessionId, sessionStorageKey]);

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
        <ScrollArea
          ref={scrollAreaRef}
          className="flex-1 min-h-0"
          onScroll={handleScroll}
        >
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

      <DeviceMonitor
        deviceId={deviceId}
        serial={deviceSerial}
        connectionType={deviceConnectionType}
        isVisible={isVisible}
      />
    </div>
  );
}
