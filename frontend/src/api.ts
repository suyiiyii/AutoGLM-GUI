import axios from 'redaxios';

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

export interface APIModelConfig {
  base_url?: string;
  api_key?: string;
  model_name?: string;
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
  frequency_penalty?: number;
}

export interface APIAgentConfig {
  max_steps?: number;
  device_id?: string | null;
  verbose?: boolean;
}

export interface InitRequest {
  model_config?: APIModelConfig;
  agent_config?: APIAgentConfig;
  // Agent 类型配置
  agent_type?: string;
  agent_config_params?: Record<string, unknown>;
  // Hot-reload support
  force?: boolean;
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

export interface ThinkingChunkEvent {
  type: 'thinking_chunk';
  role: 'assistant';
  chunk: string;
}

export interface StepEvent {
  type: 'step';
  role: 'assistant';
  step: number;
  thinking: string;
  action: Record<string, unknown>;
  success: boolean;
  finished: boolean;
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

export interface AbortedEvent {
  type: 'aborted';
  role: 'assistant';
  message: string;
}

export type StreamEvent =
  | ThinkingChunkEvent
  | StepEvent
  | DoneEvent
  | ErrorEvent
  | AbortedEvent;

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

export async function initAgent(
  config?: InitRequest
): Promise<{ success: boolean; message: string; device_id?: string }> {
  const res = await axios.post('/api/init', config ?? {});
  return res.data;
}

export async function sendMessage(message: string): Promise<ChatResponse> {
  const res = await axios.post('/api/chat', { message });
  return res.data;
}

export function sendMessageStream(
  message: string,
  deviceId: string,
  onThinkingChunk: (event: ThinkingChunkEvent) => void,
  onStep: (event: StepEvent) => void,
  onDone: (event: DoneEvent) => void,
  onError: (event: ErrorEvent) => void,
  onAborted?: (event: AbortedEvent) => void
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

      if (!response.body) {
        throw new Error('Response body is null');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let eventType = 'message'; // 移到外部，跨 chunks 保持状态

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');

        // 保留最后一行（可能不完整）
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              if (eventType === 'thinking_chunk') {
                console.log('[SSE] Received thinking_chunk event:', data);
                onThinkingChunk(data as ThinkingChunkEvent);
              } else if (eventType === 'step') {
                console.log('[SSE] Received step event:', data);
                onStep(data as StepEvent);
              } else if (eventType === 'done') {
                console.log('[SSE] Received done event:', data);
                onDone(data as DoneEvent);
              } else if (eventType === 'aborted') {
                console.log('[SSE] Received aborted event:', data);
                if (onAborted) {
                  onAborted(data as AbortedEvent);
                }
              } else if (eventType === 'error') {
                console.log('[SSE] Received error event:', data);
                onError(data as ErrorEvent);
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', line, e);
            }
          }
        }
      }
    })
    .catch(error => {
      if (error.name === 'AbortError') {
        // User manually aborted the connection
        if (onAborted) {
          onAborted({
            type: 'aborted',
            role: 'assistant',
            message: 'Connection aborted by user',
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
  default_max_steps: number;
}

export interface ConfigSaveRequest {
  base_url: string;
  model_name: string;
  api_key?: string;
  // Agent 类型配置
  agent_type?: string;
  agent_config_params?: Record<string, unknown>;
  // Agent 执行配置
  default_max_steps?: number;
}

export async function getConfig(): Promise<ConfigResponse> {
  const res = await axios.get<ConfigResponse>('/api/config');
  return res.data;
}

export async function saveConfig(
  config: ConfigSaveRequest
): Promise<{ success: boolean; message: string }> {
  const res = await axios.post('/api/config', config);
  return res.data;
}

export async function deleteConfig(): Promise<{
  success: boolean;
  message: string;
}> {
  const res = await axios.delete('/api/config');
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
