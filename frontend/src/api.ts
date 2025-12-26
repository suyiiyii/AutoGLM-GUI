import axios from 'redaxios';

export interface Device {
  id: string;
  model: string;
  status: string;
  connection_type: string;
  is_initialized: boolean;
  serial?: string; // 设备真实序列号
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

export interface StepEvent {
  type: 'step';
  step: number;
  thinking: string;
  action: Record<string, unknown>;
  success: boolean;
  finished: boolean;
}

export interface DoneEvent {
  type: 'done';
  message: string;
  steps: number;
  success: boolean;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
}

export type StreamEvent = StepEvent | DoneEvent | ErrorEvent;

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
  onStep: (event: StepEvent) => void,
  onDone: (event: DoneEvent) => void,
  onError: (event: ErrorEvent) => void
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
        throw new Error(`HTTP error! status: ${response.status}`);
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

              if (eventType === 'step') {
                console.log('[SSE] Received step event:', data);
                onStep(data as StepEvent);
              } else if (eventType === 'done') {
                console.log('[SSE] Received done event:', data);
                onDone(data as DoneEvent);
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
      if (error.name !== 'AbortError') {
        onError({ type: 'error', message: error.message });
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
}

export interface ConfigSaveRequest {
  base_url: string;
  model_name: string;
  api_key?: string;
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
