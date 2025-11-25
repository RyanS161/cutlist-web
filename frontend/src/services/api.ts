/**
 * API service for communicating with the backend.
 */

const API_BASE = '/api';

export interface Message {
  role: 'user' | 'model';
  content: string;
}

export interface ChatStreamOptions {
  message: string;
  history: Message[];
  onChunk: (chunk: string) => void;
  onError: (error: Error) => void;
  onComplete: () => void;
}

/**
 * Stream a chat response from the backend.
 * Uses Server-Sent Events (SSE) for real-time streaming.
 */
export async function streamChat({
  message,
  history,
  onChunk,
  onError,
  onComplete,
}: ChatStreamOptions): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message, history }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body reader available');
    }

    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const text = decoder.decode(value, { stream: true });
      
      // Parse SSE format: "data: <content>\n\n"
      const lines = text.split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const content = line.slice(6); // Remove "data: " prefix
          if (content && content !== '[DONE]') {
            onChunk(content);
          }
        }
      }
    }

    onComplete();
  } catch (error) {
    onError(error instanceof Error ? error : new Error(String(error)));
  }
}

/**
 * Check the health of the backend API.
 */
export async function checkHealth(): Promise<{ status: string; model: string }> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}
