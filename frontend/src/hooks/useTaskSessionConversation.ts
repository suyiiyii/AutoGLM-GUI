import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import type {
  StepTimingSummary,
  TaskEventRecordResponse,
  TaskImageAttachment,
  TaskRunResponse,
  TaskStatus,
} from '../api';
import {
  cancelTaskRun,
  createTaskSession,
  getTaskSession,
  listTaskEvents,
  listTaskSessionTasks,
  streamTaskEvents,
  submitTaskSessionTask,
} from '../api';

export interface TaskConversationMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  steps?: number;
  success?: boolean;
  thinking?: string[];
  actions?: Record<string, unknown>[];
  screenshots?: (string | undefined)[];
  stepTimings?: (StepTimingSummary | undefined)[];
  isStreaming?: boolean;
  currentThinking?: string;
  attachments?: TaskImageAttachment[];
}

interface UseTaskSessionConversationOptions {
  deviceId: string;
  deviceSerial: string;
  sessionStorageKey: string;
}

interface UseTaskSessionConversationResult {
  messages: TaskConversationMessage[];
  setMessages: Dispatch<SetStateAction<TaskConversationMessage[]>>;
  loading: boolean;
  aborting: boolean;
  waitingForDevice: boolean;
  error: string | null;
  sessionReady: boolean;
  sendMessage: (
    input: string,
    attachments?: TaskImageAttachment[]
  ) => Promise<boolean>;
  resetConversation: () => Promise<void>;
  abortConversation: () => Promise<void>;
}

function isTaskActive(status: TaskStatus): boolean {
  return status === 'QUEUED' || status === 'RUNNING';
}

function isTaskWaitingForDevice(task: TaskRunResponse): boolean {
  return task.status === 'QUEUED';
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
      typeof payload.message === 'string' ? payload.message : null;
    nextTask.error_message = null;
    nextTask.finished_at = event.created_at;
    if (typeof payload.steps === 'number') {
      nextTask.step_count = payload.steps;
    }
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
  } else if (event.event_type === 'step' && typeof payload.step === 'number') {
    nextTask.step_count = Math.max(nextTask.step_count, payload.step);
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

function buildAssistantMessage(
  task: TaskRunResponse,
  events: TaskEventRecordResponse[]
): TaskConversationMessage {
  const thinking: string[] = [];
  const actions: Record<string, unknown>[] = [];
  const screenshots: (string | undefined)[] = [];
  const stepTimings: (StepTimingSummary | undefined)[] = [];
  let currentThinking = '';
  let content = task.final_message || task.error_message || '';
  let steps = task.step_count;
  let success: boolean | undefined =
    task.status === 'SUCCEEDED'
      ? true
      : task.status === 'FAILED' ||
          task.status === 'CANCELLED' ||
          task.status === 'INTERRUPTED'
        ? false
        : undefined;

  events.forEach(event => {
    const payload = event.payload;
    switch (event.event_type) {
      case 'thinking': {
        const chunk = payload.chunk;
        if (typeof chunk === 'string') {
          currentThinking += chunk;
        }
        break;
      }
      case 'step': {
        const stepThinking =
          typeof payload.thinking === 'string' && payload.thinking.length > 0
            ? payload.thinking
            : currentThinking;
        thinking.push(stepThinking);
        actions.push((payload.action as Record<string, unknown>) || {});
        screenshots.push(
          typeof payload.screenshot === 'string'
            ? payload.screenshot
            : undefined
        );
        stepTimings.push(
          (payload.timings as StepTimingSummary | undefined) || undefined
        );
        currentThinking = '';
        if (typeof payload.step === 'number') {
          steps = payload.step;
        }
        break;
      }
      case 'done': {
        if (typeof payload.message === 'string') {
          content = payload.message;
        }
        if (typeof payload.steps === 'number') {
          steps = payload.steps;
        }
        success = payload.success === true;
        currentThinking = '';
        break;
      }
      case 'error': {
        if (typeof payload.message === 'string') {
          content = payload.message;
        }
        success = false;
        currentThinking = '';
        break;
      }
      case 'cancelled': {
        if (typeof payload.message === 'string') {
          content = payload.message;
        }
        success = false;
        currentThinking = '';
        break;
      }
    }
  });

  return {
    id: `${task.id}-agent`,
    role: 'assistant',
    content,
    timestamp: new Date(task.finished_at || task.started_at || task.created_at),
    thinking,
    actions,
    screenshots,
    stepTimings,
    steps,
    success,
    isStreaming: isTaskActive(task.status),
    currentThinking: currentThinking || undefined,
  };
}

function buildMessagePair(
  task: TaskRunResponse,
  events: TaskEventRecordResponse[]
): TaskConversationMessage[] {
  const userEvent = events.find(event => event.event_type === 'user_message');
  const userPayload = userEvent?.payload || {};
  const eventAttachments = Array.isArray(userPayload.attachments)
    ? (userPayload.attachments.filter(
        attachment =>
          attachment &&
          typeof attachment === 'object' &&
          typeof (attachment as TaskImageAttachment).mime_type === 'string' &&
          typeof (attachment as TaskImageAttachment).data === 'string'
      ) as TaskImageAttachment[])
    : [];
  const eventMessage =
    typeof userPayload.message === 'string' ? userPayload.message : null;

  return [
    {
      id: `${task.id}-user`,
      role: 'user',
      content: eventMessage ?? task.input_text,
      timestamp: new Date(task.created_at),
      attachments: eventAttachments,
    },
    buildAssistantMessage(task, events),
  ];
}

export function useTaskSessionConversation({
  deviceId,
  deviceSerial,
  sessionStorageKey,
}: UseTaskSessionConversationOptions): UseTaskSessionConversationResult {
  const [messages, setMessages] = useState<TaskConversationMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [aborting, setAborting] = useState(false);
  const [waitingForDevice, setWaitingForDevice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const chatStreamRef = useRef<{ close: () => void } | null>(null);
  const currentTaskIdRef = useRef<string | null>(null);
  const taskRunsRef = useRef<Record<string, TaskRunResponse>>({});
  const taskEventsRef = useRef<Record<string, TaskEventRecordResponse[]>>({});

  const replaceTaskMessages = useCallback((taskId: string) => {
    const task = taskRunsRef.current[taskId];
    if (!task) {
      return;
    }

    const pair = buildMessagePair(task, taskEventsRef.current[taskId] || []);
    setMessages(previousMessages => {
      const userIndex = previousMessages.findIndex(
        msg => msg.id === pair[0].id
      );
      const assistantIndex = previousMessages.findIndex(
        msg => msg.id === pair[1].id
      );

      if (userIndex === -1 || assistantIndex === -1) {
        return [...previousMessages, ...pair];
      }

      return previousMessages.map(message => {
        if (message.id === pair[0].id) {
          return pair[0];
        }
        if (message.id === pair[1].id) {
          return pair[1];
        }
        return message;
      });
    });
  }, []);

  const applyTaskEvent = useCallback(
    (taskId: string, event: TaskEventRecordResponse) => {
      const currentTask = taskRunsRef.current[taskId];
      if (!currentTask) {
        return;
      }

      taskEventsRef.current[taskId] = [
        ...(taskEventsRef.current[taskId] || []),
        event,
      ];

      const nextTask = applyTaskEventToTask(currentTask, event);
      taskRunsRef.current[taskId] = nextTask;
      setWaitingForDevice(isTaskWaitingForDevice(nextTask));
      replaceTaskMessages(taskId);

      if (
        !isTaskActive(nextTask.status) &&
        currentTaskIdRef.current === taskId
      ) {
        setLoading(false);
        setAborting(false);
        setWaitingForDevice(false);
        currentTaskIdRef.current = null;
      }
    },
    [replaceTaskMessages]
  );

  const attachTaskStream = useCallback(
    (taskId: string, afterSeq: number = 0) => {
      if (chatStreamRef.current) {
        chatStreamRef.current.close();
      }

      chatStreamRef.current = streamTaskEvents(
        taskId,
        event => {
          applyTaskEvent(taskId, event);
        },
        message => {
          setError(message);
          setLoading(false);
          setAborting(false);
          setWaitingForDevice(false);
          chatStreamRef.current = null;
        },
        afterSeq
      );
    },
    [applyTaskEvent]
  );

  const restoreSessionConversation = useCallback(
    async (targetSessionId: string) => {
      const taskList = await listTaskSessionTasks(targetSessionId, 100, 0);
      const tasks = [...taskList.tasks].reverse();

      const eventPairs = await Promise.all(
        tasks.map(
          async task =>
            [task.id, (await listTaskEvents(task.id)).events] as const
        )
      );

      taskEventsRef.current = Object.fromEntries(eventPairs);
      const reconciledTasks = tasks.map(task =>
        reconcileTaskRun(task, taskEventsRef.current[task.id] || [])
      );

      taskRunsRef.current = Object.fromEntries(
        reconciledTasks.map(task => [task.id, task])
      );
      setMessages(
        reconciledTasks.flatMap(task =>
          buildMessagePair(task, taskEventsRef.current[task.id] || [])
        )
      );

      const activeTask = [...reconciledTasks]
        .reverse()
        .find(task => isTaskActive(task.status));

      if (activeTask) {
        currentTaskIdRef.current = activeTask.id;
        setLoading(true);
        setWaitingForDevice(isTaskWaitingForDevice(activeTask));
        const lastSeq =
          taskEventsRef.current[activeTask.id]?.[
            taskEventsRef.current[activeTask.id].length - 1
          ]?.seq || 0;
        attachTaskStream(activeTask.id, lastSeq);
      } else {
        currentTaskIdRef.current = null;
        setLoading(false);
        setWaitingForDevice(false);
      }
    },
    [attachTaskStream]
  );

  useEffect(() => {
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
              existingSession.device_serial !== deviceSerial
            ) {
              nextSessionId = null;
            }
          } catch {
            nextSessionId = null;
          }
        }

        if (!nextSessionId) {
          const session = await createTaskSession(deviceId, deviceSerial);
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
          console.error('Failed to initialize task session:', sessionError);
          setError('Failed to restore chat session');
          setLoading(false);
          setWaitingForDevice(false);
        }
      }
    };

    void initializeSession();

    return () => {
      disposed = true;
      if (chatStreamRef.current) {
        chatStreamRef.current.close();
        chatStreamRef.current = null;
      }
    };
  }, [deviceId, deviceSerial, restoreSessionConversation, sessionStorageKey]);

  const sendMessage = useCallback(
    async (input: string, attachments: TaskImageAttachment[] = []) => {
      const inputValue = input.trim();
      if ((!inputValue && attachments.length === 0) || loading || !sessionId) {
        return false;
      }

      try {
        setError(null);
        setLoading(true);
        const task = await submitTaskSessionTask(
          sessionId,
          inputValue,
          attachments
        );
        const initialEvents = (await listTaskEvents(task.id)).events;
        const reconciledTask = reconcileTaskRun(task, initialEvents);

        taskRunsRef.current[task.id] = reconciledTask;
        taskEventsRef.current[task.id] = initialEvents;
        currentTaskIdRef.current = isTaskActive(reconciledTask.status)
          ? task.id
          : null;
        setWaitingForDevice(isTaskWaitingForDevice(reconciledTask));
        replaceTaskMessages(task.id);

        if (isTaskActive(reconciledTask.status)) {
          const lastSeq = initialEvents[initialEvents.length - 1]?.seq || 0;
          attachTaskStream(task.id, lastSeq);
        } else {
          setLoading(false);
          setAborting(false);
          setWaitingForDevice(false);
        }

        return true;
      } catch (sendError) {
        console.error('Failed to submit task:', sendError);
        setLoading(false);
        setError(
          sendError instanceof Error
            ? sendError.message
            : 'Failed to submit task'
        );
        return false;
      }
    },
    [attachTaskStream, loading, replaceTaskMessages, sessionId]
  );

  const resetConversation = useCallback(async () => {
    if (chatStreamRef.current) {
      chatStreamRef.current.close();
      chatStreamRef.current = null;
    }

    try {
      const session = await createTaskSession(deviceId, deviceSerial);
      sessionStorage.setItem(sessionStorageKey, session.id);
      setSessionId(session.id);
      taskRunsRef.current = {};
      taskEventsRef.current = {};
      currentTaskIdRef.current = null;
      setMessages([]);
      setLoading(false);
      setWaitingForDevice(false);
      setError(null);
      setAborting(false);
    } catch (resetError) {
      console.error('Failed to reset chat session:', resetError);
      setError(
        resetError instanceof Error
          ? resetError.message
          : 'Failed to reset chat'
      );
    }
  }, [deviceId, deviceSerial, sessionStorageKey]);

  const abortConversation = useCallback(async () => {
    const taskId = currentTaskIdRef.current;
    if (!taskId) {
      return;
    }

    setAborting(true);
    try {
      const response = await cancelTaskRun(taskId);
      if (response.task) {
        taskRunsRef.current[taskId] = response.task;
        setWaitingForDevice(isTaskWaitingForDevice(response.task));
        replaceTaskMessages(taskId);
      }
    } catch (abortError) {
      console.error('Failed to abort chat:', abortError);
      setAborting(false);
      setError(
        abortError instanceof Error
          ? abortError.message
          : 'Failed to cancel task'
      );
    }
  }, [replaceTaskMessages]);

  useEffect(() => {
    return () => {
      if (chatStreamRef.current) {
        chatStreamRef.current.close();
      }
    };
  }, [deviceId]);

  return {
    messages,
    setMessages,
    loading,
    aborting,
    waitingForDevice,
    error,
    sessionReady: sessionId !== null,
    sendMessage,
    resetConversation,
    abortConversation,
  };
}
