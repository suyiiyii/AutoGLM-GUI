import axios from 'redaxios';
import { readServerEventStream } from './lib/sse';

/**
 * 从 axios/redaxios 错误中提取详细的错误信息
 * 优先返回后端 FastAPI HTTPException 的 detail 字段
 */
export function getErrorMessage(error: unknown): string {
  if (error && typeof error === 'object') {
    // redaxios 错误格式: { data: { detail: string }, status: number }
    const axiosError = error as {
      data?: { detail?: string };
      status?: number;
      message?: string;
    };

    // 优先使用后端返回的 detail 字段
    if (axiosError.data?.detail) {
      return axiosError.data.detail;
    }

    // 其次使用 message 字段
    if (axiosError.message) {
      return axiosError.message;
    }

    // 如果有状态码，返回状态码信息
    if (axiosError.status) {
      return `HTTP error! status: ${axiosError.status}`;
    }
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'Unknown error';
}

export interface AgentStatus {
  state: 'idle' | 'busy' | 'error' | 'initializing';
  created_at: number;
  last_used: number;
  error_message: string | null;
  model_name: string;
}

export interface Device {
  id: string;
  serial: string; // Hardware serial number (always present)
  model: string;
  status: string;
  connection_type: string;
  state: string;
  is_available_only: boolean;
  display_name: string | null; // Custom display name (null if not set)
  group_id: string; // Device group ID (default: "default")
  agent: AgentStatus | null; // Agent runtime status (null if not initialized)
}

export interface DeviceListResponse {
  devices: Device[];
}

export interface ChatResponse {
  result: string;
  steps: number;
  success: boolean;
}

export interface StatusResponse {
  version: string;
  initialized: boolean;
  step_count: number;
}

export interface ScreenshotRequest {
  device_id?: string | null;
}

export interface ScreenshotResponse {
  success: boolean;
  image: string; // base64 encoded PNG
  width: number;
  height: number;
  is_sensitive: boolean;
  error?: string;
}

export interface ThinkingEvent {
  type: 'thinking';
  role: 'assistant';
  chunk: string;
}

export interface StepTimingSummary {
  step: number;
  trace_id: string;
  total_duration_ms: number;
  screenshot_duration_ms: number;
  current_app_duration_ms: number;
  llm_duration_ms: number;
  parse_action_duration_ms: number;
  execute_action_duration_ms: number;
  update_context_duration_ms: number;
  adb_duration_ms: number;
  sleep_duration_ms: number;
  other_duration_ms: number;
}

export interface TraceTimingSummary {
  trace_id: string;
  steps: number;
  total_duration_ms: number;
  screenshot_duration_ms: number;
  current_app_duration_ms: number;
  llm_duration_ms: number;
  parse_action_duration_ms: number;
  execute_action_duration_ms: number;
  update_context_duration_ms: number;
  adb_duration_ms: number;
  sleep_duration_ms: number;
  other_duration_ms: number;
}

export interface StepEvent {
  type: 'step';
  role: 'assistant';
  step: number;
  thinking: string;
  action: Record<string, unknown>;
  success: boolean;
  finished: boolean;
  screenshot?: string;
  timings?: StepTimingSummary;
}

export interface DoneEvent {
  type: 'done';
  role: 'assistant';
  message: string;
  steps: number;
  success: boolean;
}

export interface ErrorEvent {
  type: 'error';
  role: 'assistant';
  message: string;
}

export interface CancelledEvent {
  type: 'cancelled';
  role: 'assistant';
  message: string;
}

export type StreamEvent =
  | ThinkingEvent
  | StepEvent
  | DoneEvent
  | ErrorEvent
  | CancelledEvent;

export interface TapRequest {
  x: number;
  y: number;
  device_id?: string | null;
  delay?: number;
}

export interface TapResponse {
  success: boolean;
  error?: string;
}

export interface SwipeRequest {
  start_x: number;
  start_y: number;
  end_x: number;
  end_y: number;
  duration_ms?: number;
  device_id?: string | null;
  delay?: number;
}

export interface SwipeResponse {
  success: boolean;
  error?: string;
}

export interface TouchDownRequest {
  x: number;
  y: number;
  device_id?: string | null;
  delay?: number;
}

export interface TouchDownResponse {
  success: boolean;
  error?: string;
}

export interface TouchMoveRequest {
  x: number;
  y: number;
  device_id?: string | null;
  delay?: number;
}

export interface TouchMoveResponse {
  success: boolean;
  error?: string;
}

export interface TouchUpRequest {
  x: number;
  y: number;
  device_id?: string | null;
  delay?: number;
}

export interface TouchUpResponse {
  success: boolean;
  error?: string;
}

export interface WiFiConnectRequest {
  device_id?: string | null;
  port?: number;
}

export interface WiFiConnectResponse {
  success: boolean;
  message: string;
  device_id?: string;
  address?: string;
  error?: string;
}

export interface WiFiDisconnectResponse {
  success: boolean;
  message: string;
  error?: string;
}

export interface WiFiManualConnectRequest {
  ip: string;
  port?: number;
}

export interface WiFiManualConnectResponse {
  success: boolean;
  message: string;
  device_id?: string;
  error?: string;
}

export interface WiFiPairRequest {
  ip: string;
  pairing_port: number;
  pairing_code: string;
  connection_port?: number;
}

export interface WiFiPairResponse {
  success: boolean;
  message: string;
  device_id?: string;
  error?: string;
}

export interface MdnsDevice {
  name: string;
  ip: string;
  port: number;
  has_pairing: boolean;
  service_type: string;
  pairing_port?: number;
}

export interface MdnsDiscoverResponse {
  success: boolean;
  devices: MdnsDevice[];
  error?: string;
}

export interface RemoteDeviceInfo {
  device_id: string;
  model: string;
  platform: string;
  status: string;
}

export interface RemoteDeviceDiscoverRequest {
  base_url: string;
  timeout?: number;
}

export interface RemoteDeviceDiscoverResponse {
  success: boolean;
  devices: RemoteDeviceInfo[];
  message: string;
  error?: string;
}

export interface RemoteDeviceAddRequest {
  base_url: string;
  device_id: string;
}

export interface RemoteDeviceAddResponse {
  success: boolean;
  message: string;
  serial?: string;
  error?: string;
}

export interface RemoteDeviceRemoveRequest {
  serial: string;
}

export interface RemoteDeviceRemoveResponse {
  success: boolean;
  message: string;
  error?: string;
}

export interface TerminalSessionCreateRequest {
  cwd?: string;
  command?: string[];
}

export interface TerminalSession {
  session_id: string;
  cwd: string;
  command: string[];
  status: string;
  created_at: number;
  last_active_at: number;
  exit_code?: number | null;
  created_by?: string | null;
  origin?: string | null;
  owner_token_hash?: string | null;
  total_output_bytes: number;
}

export interface TerminalSessionCreateResponse extends TerminalSession {
  session_token: string;
}

export interface TerminalSessionCloseResponse {
  success: boolean;
  message: string;
  session_id: string;
}

export async function listDevices(): Promise<DeviceListResponse> {
  const res = await axios.get<DeviceListResponse>('/api/devices');
  return res.data;
}

export async function getDevices(): Promise<Device[]> {
  const response = await axios.get<DeviceListResponse>('/api/devices');
  return response.data.devices;
}

export async function connectWifi(
  payload: WiFiConnectRequest
): Promise<WiFiConnectResponse> {
  const res = await axios.post<WiFiConnectResponse>(
    '/api/devices/connect_wifi',
    payload
  );
  return res.data;
}

export async function disconnectWifi(
  deviceId: string
): Promise<WiFiDisconnectResponse> {
  const response = await axios.post<WiFiDisconnectResponse>(
    '/api/devices/disconnect_wifi',
    {
      device_id: deviceId,
    }
  );
  return response.data;
}

export async function connectWifiManual(
  payload: WiFiManualConnectRequest
): Promise<WiFiManualConnectResponse> {
  const res = await axios.post<WiFiManualConnectResponse>(
    '/api/devices/connect_wifi_manual',
    payload
  );
  return res.data;
}

export async function pairWifi(
  payload: WiFiPairRequest
): Promise<WiFiPairResponse> {
  const res = await axios.post<WiFiPairResponse>(
    '/api/devices/pair_wifi',
    payload
  );
  return res.data;
}

export async function discoverRemoteDevices(
  payload: RemoteDeviceDiscoverRequest
): Promise<RemoteDeviceDiscoverResponse> {
  const res = await axios.post<RemoteDeviceDiscoverResponse>(
    '/api/devices/discover_remote',
    payload
  );
  return res.data;
}

export async function addRemoteDevice(
  payload: RemoteDeviceAddRequest
): Promise<RemoteDeviceAddResponse> {
  const res = await axios.post<RemoteDeviceAddResponse>(
    '/api/devices/add_remote',
    payload
  );
  return res.data;
}

export async function removeRemoteDevice(
  serial: string
): Promise<RemoteDeviceRemoveResponse> {
  const res = await axios.post<RemoteDeviceRemoveResponse>(
    '/api/devices/remove_remote',
    { serial }
  );
  return res.data;
}

export async function createTerminalSession(
  payload: TerminalSessionCreateRequest = {}
): Promise<TerminalSessionCreateResponse> {
  const res = await axios.post<TerminalSessionCreateResponse>(
    '/api/terminal/sessions',
    payload
  );
  return res.data;
}

export async function getTerminalSession(
  sessionId: string,
  sessionToken: string
): Promise<TerminalSession> {
  const res = await axios.get<TerminalSession>(
    `/api/terminal/sessions/${sessionId}`,
    {
      params: { token: sessionToken },
    }
  );
  return res.data;
}

export async function closeTerminalSession(
  sessionId: string,
  sessionToken: string
): Promise<TerminalSessionCloseResponse> {
  const res = await axios.delete<TerminalSessionCloseResponse>(
    `/api/terminal/sessions/${sessionId}`,
    {
      params: { token: sessionToken },
    }
  );
  return res.data;
}

export async function sendMessage(message: string): Promise<ChatResponse> {
  const res = await axios.post('/api/chat', { message });
  return res.data;
}

export function sendMessageStream(
  message: string,
  deviceId: string,
  onThinking: (event: ThinkingEvent) => void,
  onStep: (event: StepEvent) => void,
  onDone: (event: DoneEvent) => void,
  onError: (event: ErrorEvent) => void,
  onCancelled?: (event: CancelledEvent) => void
): { close: () => void } {
  const controller = new AbortController();

  fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, device_id: deviceId }),
    signal: controller.signal,
  })
    .then(async response => {
      await readServerEventStream(
        response,
        (eventType, data) => {
          if (eventType === 'thinking') {
            onThinking(data as ThinkingEvent);
          } else if (eventType === 'step') {
            onStep(data as StepEvent);
          } else if (eventType === 'done') {
            onDone(data as DoneEvent);
          } else if (eventType === 'cancelled') {
            if (onCancelled) {
              onCancelled(data as CancelledEvent);
            }
          } else if (eventType === 'error') {
            onError(data as ErrorEvent);
          }
        },
        'Failed to parse SSE data:'
      );
    })
    .catch(error => {
      if (error.name === 'AbortError') {
        // User manually cancelled the connection
        if (onCancelled) {
          onCancelled({
            type: 'cancelled',
            role: 'assistant',
            message: 'Task cancelled by user',
          });
        }
      } else {
        onError({ type: 'error', role: 'assistant', message: error.message });
      }
    });

  return {
    close: () => controller.abort(),
  };
}

export async function getStatus(): Promise<StatusResponse> {
  const res = await axios.get('/api/status');
  return res.data;
}

export async function resetChat(deviceId: string): Promise<{
  success: boolean;
  message: string;
  device_id?: string;
}> {
  const res = await axios.post('/api/reset', { device_id: deviceId });
  return res.data;
}

export async function abortChat(deviceId: string): Promise<{
  success: boolean;
  message: string;
}> {
  const res = await axios.post('/api/chat/abort', { device_id: deviceId });
  return res.data;
}

export async function getScreenshot(
  deviceId?: string | null
): Promise<ScreenshotResponse> {
  const res = await axios.post(
    '/api/screenshot',
    { device_id: deviceId ?? null },
    {}
  );
  return res.data;
}

export async function sendTap(
  x: number,
  y: number,
  deviceId?: string | null,
  delay: number = 0
): Promise<TapResponse> {
  const res = await axios.post<TapResponse>('/api/control/tap', {
    x,
    y,
    device_id: deviceId ?? null,
    delay,
  });
  return res.data;
}

export async function sendSwipe(
  startX: number,
  startY: number,
  endX: number,
  endY: number,
  durationMs?: number,
  deviceId?: string | null,
  delay: number = 0
): Promise<SwipeResponse> {
  const swipeData = {
    start_x: Math.round(startX),
    start_y: Math.round(startY),
    end_x: Math.round(endX),
    end_y: Math.round(endY),
    duration_ms: Math.round(durationMs || 300),
    device_id: deviceId ?? null,
    delay: Math.round(delay * 1000) / 1000,
  };

  try {
    const res = await axios.post<SwipeResponse>(
      '/api/control/swipe',
      swipeData
    );
    return res.data;
  } catch (error) {
    console.error('[API] Swipe request failed:', error);
    throw error;
  }
}

export async function sendTouchDown(
  x: number,
  y: number,
  deviceId?: string | null,
  delay: number = 0
): Promise<TouchDownResponse> {
  const res = await axios.post<TouchDownResponse>('/api/control/touch/down', {
    x: Math.round(x),
    y: Math.round(y),
    device_id: deviceId ?? null,
    delay,
  });
  return res.data;
}

export async function sendTouchMove(
  x: number,
  y: number,
  deviceId?: string | null,
  delay: number = 0
): Promise<TouchMoveResponse> {
  const res = await axios.post<TouchMoveResponse>('/api/control/touch/move', {
    x: Math.round(x),
    y: Math.round(y),
    device_id: deviceId ?? null,
    delay,
  });
  return res.data;
}

export async function sendTouchUp(
  x: number,
  y: number,
  deviceId?: string | null,
  delay: number = 0
): Promise<TouchUpResponse> {
  const res = await axios.post<TouchUpResponse>('/api/control/touch/up', {
    x: Math.round(x),
    y: Math.round(y),
    device_id: deviceId ?? null,
    delay,
  });
  return res.data;
}

// Configuration Management

export interface ConfigResponse {
  base_url: string;
  model_name: string;
  api_key: string;
  source: string;
  // Agent 类型配置
  agent_type?: string;
  agent_config_params?: Record<string, unknown>;
  // Agent 执行配置
  default_max_steps: number | null;
  layered_max_turns: number;
  // 决策模型配置
  decision_base_url?: string;
  decision_model_name?: string;
  decision_api_key?: string;
}

export interface ConfigSaveRequest {
  base_url: string;
  model_name: string;
  api_key?: string;
  // Agent 类型配置
  agent_type?: string;
  agent_config_params?: Record<string, unknown>;
  // Agent 执行配置
  default_max_steps?: number | null;
  layered_max_turns?: number;
  // 决策模型配置
  decision_base_url?: string;
  decision_model_name?: string;
  decision_api_key?: string;
}

export interface ConfigSaveResponse {
  success: boolean;
  message: string;
  restart_required?: boolean;
  warnings?: string[];
}

export async function getConfig(): Promise<ConfigResponse> {
  const res = await axios.get<ConfigResponse>('/api/config');
  return res.data;
}

export async function saveConfig(
  config: ConfigSaveRequest
): Promise<ConfigSaveResponse> {
  const res = await axios.post<ConfigSaveResponse>('/api/config', config);
  return res.data;
}

export async function deleteConfig(): Promise<{
  success: boolean;
  message: string;
}> {
  const res = await axios.delete('/api/config');
  return res.data;
}

export interface ReinitAllAgentsResponse {
  success: boolean;
  total: number;
  succeeded: string[];
  failed: Record<string, string>;
  message: string;
}

export async function reinitAllAgents(): Promise<ReinitAllAgentsResponse> {
  const res = await axios.post<ReinitAllAgentsResponse>(
    '/api/agents/reinit-all'
  );
  return res.data;
}

export interface VersionCheckResponse {
  current_version: string;
  latest_version: string | null;
  has_update: boolean;
  release_url: string | null;
  published_at: string | null;
  error: string | null;
}

export async function checkVersion(): Promise<VersionCheckResponse> {
  const res = await axios.get<VersionCheckResponse>('/api/version/latest');
  return res.data;
}

export async function discoverMdnsDevices(): Promise<MdnsDiscoverResponse> {
  const res = await axios.get<MdnsDiscoverResponse>(
    '/api/devices/discover_mdns'
  );
  return res.data;
}

// QR Code Pairing

export interface QRPairGenerateResponse {
  success: boolean;
  qr_payload?: string;
  session_id?: string;
  expires_at?: number;
  message: string;
  error?: string;
}

export interface QRPairStatusResponse {
  session_id: string;
  status: string; // "listening" | "pairing" | "paired" | "connecting" | "connected" | "timeout" | "error"
  device_id?: string;
  message: string;
  error?: string;
}

export interface QRPairCancelResponse {
  success: boolean;
  message: string;
}

export async function generateQRPairing(
  timeout: number = 90
): Promise<QRPairGenerateResponse> {
  const res = await axios.post<QRPairGenerateResponse>(
    '/api/devices/qr_pair/generate',
    { timeout }
  );
  return res.data;
}

export async function getQRPairingStatus(
  sessionId: string
): Promise<QRPairStatusResponse> {
  const res = await axios.get<QRPairStatusResponse>(
    `/api/devices/qr_pair/status/${sessionId}`
  );
  return res.data;
}

export async function cancelQRPairing(
  sessionId: string
): Promise<QRPairCancelResponse> {
  const res = await axios.delete<QRPairCancelResponse>(
    `/api/devices/qr_pair/${sessionId}`
  );
  return res.data;
}

// ==================== Workflow API ====================

export interface Workflow {
  uuid: string;
  name: string;
  text: string;
}

export interface WorkflowListResponse {
  workflows: Workflow[];
}

export interface WorkflowCreateRequest {
  name: string;
  text: string;
}

export interface WorkflowUpdateRequest {
  name: string;
  text: string;
}

export async function listWorkflows(): Promise<WorkflowListResponse> {
  const res = await axios.get<WorkflowListResponse>('/api/workflows');
  return res.data;
}

export async function getWorkflow(uuid: string): Promise<Workflow> {
  const res = await axios.get<Workflow>(`/api/workflows/${uuid}`);
  return res.data;
}

export async function createWorkflow(
  request: WorkflowCreateRequest
): Promise<Workflow> {
  const res = await axios.post<Workflow>('/api/workflows', request);
  return res.data;
}

export async function updateWorkflow(
  uuid: string,
  request: WorkflowUpdateRequest
): Promise<Workflow> {
  const res = await axios.put<Workflow>(`/api/workflows/${uuid}`, request);
  return res.data;
}

export async function deleteWorkflow(uuid: string): Promise<void> {
  await axios.delete(`/api/workflows/${uuid}`);
}

// ==================== Task API ====================

export type TaskStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELLED'
  | 'INTERRUPTED';

export interface TaskSessionResponse {
  id: string;
  kind: string;
  mode: string;
  device_id: string;
  device_serial: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TaskRunResponse {
  id: string;
  source: string;
  executor_key: string;
  session_id: string | null;
  scheduled_task_id: string | null;
  workflow_uuid: string | null;
  schedule_fire_id: string | null;
  device_id: string;
  device_serial: string;
  status: TaskStatus;
  input_text: string;
  final_message: string | null;
  error_message: string | null;
  stop_reason: string | null;
  trace_id: string | null;
  step_count: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface TaskRunListResponse {
  tasks: TaskRunResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface TaskEventRecordResponse {
  task_id: string;
  seq: number;
  event_type: string;
  role: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface TaskEventListResponse {
  events: TaskEventRecordResponse[];
}

export interface TaskImageAttachment {
  mime_type: string;
  data: string;
  name?: string | null;
}

export interface TaskCancelResponse {
  success: boolean;
  message: string;
  task: TaskRunResponse | null;
}

export interface TaskSessionResetResponse {
  success: boolean;
  message: string;
  session: TaskSessionResponse | null;
}

export async function createTaskSession(
  deviceId: string,
  deviceSerial: string,
  mode: 'classic' | 'layered' = 'classic'
): Promise<TaskSessionResponse> {
  const res = await axios.post<TaskSessionResponse>('/api/task-sessions', {
    device_id: deviceId,
    device_serial: deviceSerial,
    mode,
  });
  return res.data;
}

export async function getTaskSession(
  sessionId: string
): Promise<TaskSessionResponse> {
  const res = await axios.get<TaskSessionResponse>(
    `/api/task-sessions/${sessionId}`
  );
  return res.data;
}

export async function resetTaskSession(
  sessionId: string
): Promise<TaskSessionResetResponse> {
  const res = await axios.post<TaskSessionResetResponse>(
    `/api/task-sessions/${sessionId}/reset`
  );
  return res.data;
}

export async function listTaskSessionTasks(
  sessionId: string,
  limit: number = 50,
  offset: number = 0
): Promise<TaskRunListResponse> {
  const res = await axios.get<TaskRunListResponse>(
    `/api/task-sessions/${sessionId}/tasks`,
    { params: { limit, offset } }
  );
  return res.data;
}

export async function submitTaskSessionTask(
  sessionId: string,
  message: string,
  attachments: TaskImageAttachment[] = []
): Promise<TaskRunResponse> {
  const res = await axios.post<TaskRunResponse>(
    `/api/task-sessions/${sessionId}/tasks`,
    { message, attachments }
  );
  return res.data;
}

export async function getTask(taskId: string): Promise<TaskRunResponse> {
  const res = await axios.get<TaskRunResponse>(`/api/tasks/${taskId}`);
  return res.data;
}

export async function listTaskEvents(
  taskId: string,
  afterSeq: number = 0
): Promise<TaskEventListResponse> {
  const res = await axios.get<TaskEventListResponse>(
    `/api/tasks/${taskId}/events`,
    { params: { after_seq: afterSeq } }
  );
  return res.data;
}

export async function cancelTaskRun(
  taskId: string
): Promise<TaskCancelResponse> {
  const res = await axios.post<TaskCancelResponse>(
    `/api/tasks/${taskId}/cancel`
  );
  return res.data;
}

export function streamTaskEvents(
  taskId: string,
  onEvent: (event: TaskEventRecordResponse) => void,
  onError?: (message: string) => void,
  afterSeq: number = 0
): { close: () => void } {
  const controller = new AbortController();

  fetch(`/api/tasks/${taskId}/stream?after_seq=${afterSeq}`, {
    method: 'GET',
    signal: controller.signal,
  })
    .then(async response => {
      await readServerEventStream(
        response,
        (eventType, data) => {
          onEvent({
            ...(data as TaskEventRecordResponse),
            event_type:
              (data as TaskEventRecordResponse).event_type || eventType,
          });
        },
        'Failed to parse task SSE data:'
      );
    })
    .catch(error => {
      if (error.name === 'AbortError') {
        return;
      }
      if (onError) {
        onError(error.message);
      }
    });

  return {
    close: () => controller.abort(),
  };
}

// ==================== Layered Agent API ====================

export async function abortLayeredAgentChat(sessionId: string): Promise<{
  success: boolean;
  message: string;
}> {
  const res = await axios.post('/api/layered-agent/abort', {
    session_id: sessionId,
  });
  return res.data;
}

// ==================== History API ====================

export interface MessageRecordResponse {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  thinking?: string | null;
  action?: Record<string, unknown> | null;
  step?: number | null;
  attachments?: TaskImageAttachment[];
}

export interface HistoryRecordResponse {
  id: string;
  task_text: string;
  final_message: string;
  success: boolean;
  steps: number;
  start_time: string;
  end_time: string | null;
  duration_ms: number;
  source: 'chat' | 'layered' | 'scheduled';
  source_detail: string;
  error_message: string | null;
  trace_id?: string | null;
  step_timings: StepTimingSummary[];
  trace_summary?: TraceTimingSummary | null;
  messages: MessageRecordResponse[];
}

export interface HistoryListResponse {
  records: HistoryRecordResponse[];
  total: number;
  limit: number;
  offset: number;
}

export async function listHistory(
  serialno: string,
  limit: number = 50,
  offset: number = 0,
  mode?: 'classic' | 'layered'
): Promise<HistoryListResponse> {
  const res = await axios.get<HistoryListResponse>(`/api/history/${serialno}`, {
    params: { limit, offset, ...(mode ? { mode } : {}) },
  });
  return res.data;
}

export async function getHistoryRecord(
  serialno: string,
  recordId: string
): Promise<HistoryRecordResponse> {
  const res = await axios.get<HistoryRecordResponse>(
    `/api/history/${serialno}/${recordId}`
  );
  return res.data;
}

export async function deleteHistoryRecord(
  serialno: string,
  recordId: string
): Promise<void> {
  await axios.delete(`/api/history/${serialno}/${recordId}`);
}

export async function clearHistory(serialno: string): Promise<void> {
  await axios.delete(`/api/history/${serialno}`);
}

// ==================== Scheduled Tasks API ====================

export interface ScheduledTaskResponse {
  id: string;
  name: string;
  workflow_uuid: string;
  device_serialnos: string[];
  device_group_id?: string | null;
  cron_expression: string;
  enabled: boolean;
  execution_mode: 'classic' | 'layered';
  created_at: string;
  updated_at: string;
  last_run_time: string | null;
  last_run_success: boolean | null;
  last_run_status?: 'success' | 'partial' | 'failure' | null;
  last_run_success_count?: number | null;
  last_run_total_count?: number | null;
  last_run_message: string | null;
  next_run_time: string | null;
}

export interface ScheduledTaskListResponse {
  tasks: ScheduledTaskResponse[];
}

export interface ScheduledTaskCreate {
  name: string;
  workflow_uuid: string;
  device_serialnos?: string[] | null;
  device_group_id?: string | null;
  cron_expression: string;
  enabled?: boolean;
  execution_mode?: 'classic' | 'layered';
}

export interface ScheduledTaskUpdate {
  name?: string;
  workflow_uuid?: string;
  device_serialnos?: string[] | null;
  device_group_id?: string | null;
  cron_expression?: string;
  enabled?: boolean;
  execution_mode?: 'classic' | 'layered';
}

export async function listScheduledTasks(): Promise<ScheduledTaskListResponse> {
  const res = await axios.get<ScheduledTaskListResponse>(
    '/api/scheduled-tasks'
  );
  return res.data;
}

export async function createScheduledTask(
  data: ScheduledTaskCreate
): Promise<ScheduledTaskResponse> {
  const res = await axios.post<ScheduledTaskResponse>(
    '/api/scheduled-tasks',
    data
  );
  return res.data;
}

export async function getScheduledTask(
  taskId: string
): Promise<ScheduledTaskResponse> {
  const res = await axios.get<ScheduledTaskResponse>(
    `/api/scheduled-tasks/${taskId}`
  );
  return res.data;
}

export async function updateScheduledTask(
  taskId: string,
  data: ScheduledTaskUpdate
): Promise<ScheduledTaskResponse> {
  const res = await axios.put<ScheduledTaskResponse>(
    `/api/scheduled-tasks/${taskId}`,
    data
  );
  return res.data;
}

export async function deleteScheduledTask(taskId: string): Promise<void> {
  await axios.delete(`/api/scheduled-tasks/${taskId}`);
}

export async function enableScheduledTask(
  taskId: string
): Promise<ScheduledTaskResponse> {
  const res = await axios.post<ScheduledTaskResponse>(
    `/api/scheduled-tasks/${taskId}/enable`
  );
  return res.data;
}

export async function disableScheduledTask(
  taskId: string
): Promise<ScheduledTaskResponse> {
  const res = await axios.post<ScheduledTaskResponse>(
    `/api/scheduled-tasks/${taskId}/disable`
  );
  return res.data;
}

export interface DeviceNameResponse {
  success: boolean;
  serial: string;
  display_name: string | null;
  error?: string;
}

export async function updateDeviceName(
  serial: string,
  displayName: string | null
): Promise<DeviceNameResponse> {
  const res = await axios.put<DeviceNameResponse>(
    `/api/devices/${serial}/name`,
    { display_name: displayName }
  );
  return res.data;
}

export async function getDeviceName(
  serial: string
): Promise<DeviceNameResponse> {
  const res = await axios.get<DeviceNameResponse>(
    `/api/devices/${serial}/name`
  );
  return res.data;
}

// ==================== Device Group API ====================

export interface DeviceGroup {
  id: string;
  name: string;
  order: number;
  created_at: string;
  updated_at: string;
  is_default: boolean;
  device_count: number;
}

export interface DeviceGroupListResponse {
  groups: DeviceGroup[];
}

export interface DeviceGroupOperationResponse {
  success: boolean;
  message: string;
  error?: string;
}

export async function listDeviceGroups(): Promise<DeviceGroupListResponse> {
  const res = await axios.get<DeviceGroupListResponse>('/api/device-groups');
  return res.data;
}

export async function createDeviceGroup(name: string): Promise<DeviceGroup> {
  const res = await axios.post<DeviceGroup>('/api/device-groups', { name });
  return res.data;
}

export async function updateDeviceGroup(
  groupId: string,
  name: string
): Promise<DeviceGroup> {
  const res = await axios.put<DeviceGroup>(`/api/device-groups/${groupId}`, {
    name,
  });
  return res.data;
}

export async function deleteDeviceGroup(
  groupId: string
): Promise<DeviceGroupOperationResponse> {
  const res = await axios.delete<DeviceGroupOperationResponse>(
    `/api/device-groups/${groupId}`
  );
  return res.data;
}

export async function reorderDeviceGroups(
  groupIds: string[]
): Promise<DeviceGroupOperationResponse> {
  const res = await axios.put<DeviceGroupOperationResponse>(
    '/api/device-groups/reorder',
    { group_ids: groupIds }
  );
  return res.data;
}

export async function assignDeviceToGroup(
  serial: string,
  groupId: string
): Promise<DeviceGroupOperationResponse> {
  const res = await axios.put<DeviceGroupOperationResponse>(
    `/api/devices/${serial}/group`,
    { group_id: groupId }
  );
  return res.data;
}
