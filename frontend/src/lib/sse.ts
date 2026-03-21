async function getResponseErrorDetail(response: Response): Promise<string> {
  let errorDetail = `HTTP error! status: ${response.status}`;

  try {
    const errorData = await response.json();
    if (errorData.detail) {
      errorDetail = errorData.detail;
    }
  } catch {
    // Ignore invalid error body and fall back to the status-based message.
  }

  return errorDetail;
}

export async function readServerEventStream(
  response: Response,
  onEvent: (eventType: string, data: unknown) => void,
  parseErrorLabel: string
): Promise<void> {
  if (!response.ok) {
    throw new Error(await getResponseErrorDetail(response));
  }

  if (!response.body) {
    throw new Error('Response body is null');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let eventType = 'message';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        try {
          onEvent(eventType, JSON.parse(line.slice(6)));
        } catch (error) {
          console.error(parseErrorLabel, error, line);
        }
      }
    }
  }
}
