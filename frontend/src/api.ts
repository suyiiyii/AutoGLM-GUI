import axios from 'redaxios';

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
  action: Record<string, any>;
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

export async function initAgent(
  config?: InitRequest
): Promise<{ success: boolean; message: string }> {
  const res = await axios.post('/api/init', config ?? {});
  return res.data;
}

export async function sendMessage(message: string): Promise<ChatResponse> {
  const res = await axios.post('/api/chat', { message });
  return res.data;
}

export function sendMessageStream(
  message: string,
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
    body: JSON.stringify({ message }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body!.getReader();
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
    .catch((error) => {
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

export async function resetChat(): Promise<{
  success: boolean;
  message: string;
}> {
  const res = await axios.post('/api/reset');
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
