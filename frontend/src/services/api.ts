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
  systemPrompt?: string;
  currentCode?: string;
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
  systemPrompt,
  currentCode,
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
      body: JSON.stringify({ 
        message, 
        history, 
        system_prompt: systemPrompt,
        current_code: currentCode,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body reader available');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      
      // SSE messages are separated by double newlines
      // Each message can have multiple "data:" lines that should be joined with newlines
      const messages = buffer.split(/\r?\n\r?\n/);
      
      // Keep the last incomplete message in the buffer
      buffer = messages.pop() || '';
      
      for (const message of messages) {
        if (!message.trim()) continue;
        
        // Collect all data lines in this message and join them with newlines
        const dataLines: string[] = [];
        const lines = message.split(/\r?\n/);
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            dataLines.push(line.slice(6)); // Remove "data: " prefix
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5)); // Handle "data:" without space (empty line)
          }
        }
        
        if (dataLines.length > 0) {
          const content = dataLines.join('\n');
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

export interface ExecuteCodeResult {
  success: boolean;
  output: string;
  error?: string;
  result?: string;
  stl_url?: string;
}

/**
 * Execute Python code on the backend.
 */
export async function executeCode(code: string): Promise<ExecuteCodeResult> {
  const response = await fetch(`${API_BASE}/execute`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ code }),
  });
  
  if (!response.ok) {
    throw new Error(`Code execution failed: ${response.status}`);
  }
  
  return response.json();
}

/**
 * Get the default system prompt from the backend.
 */
export async function getDefaultSystemPrompt(): Promise<string> {
  const response = await fetch(`${API_BASE}/system-prompt`);
  if (!response.ok) {
    throw new Error(`Failed to fetch system prompt: ${response.status}`);
  }
  const data = await response.json();
  return data.system_prompt;
}
