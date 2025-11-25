import { useState, useCallback, useRef } from 'react';
import type { Message } from '../services/api';
import { streamChat } from '../services/api';

interface UseChatOptions {
  systemPrompt?: string;
}

interface UseChatReturn {
  messages: Message[];
  isStreaming: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  clearChat: () => void;
  chatStarted: boolean;
}

/**
 * Custom hook for managing chat state and streaming messages.
 */
export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatStarted, setChatStarted] = useState(false);
  
  // Use ref to track current messages during streaming
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;
  
  // Store the system prompt for this chat session
  const systemPromptRef = useRef<string | undefined>(options.systemPrompt);
  systemPromptRef.current = options.systemPrompt;

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isStreaming) return;

    setError(null);
    setChatStarted(true);
    
    // Add user message
    const userMessage: Message = { role: 'user', content: content.trim() };
    const updatedMessages = [...messagesRef.current, userMessage];
    setMessages(updatedMessages);
    
    // Add placeholder for assistant response
    const assistantMessage: Message = { role: 'model', content: '' };
    setMessages([...updatedMessages, assistantMessage]);
    
    setIsStreaming(true);

    await streamChat({
      message: content.trim(),
      history: updatedMessages.slice(0, -1), // Don't include the message we just added
      systemPrompt: systemPromptRef.current,
      onChunk: (chunk) => {
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (updated[lastIdx]?.role === 'model') {
            updated[lastIdx] = {
              ...updated[lastIdx],
              content: updated[lastIdx].content + chunk,
            };
          }
          return updated;
        });
      },
      onError: (err) => {
        setError(err.message);
        setIsStreaming(false);
      },
      onComplete: () => {
        setIsStreaming(false);
      },
    });
  }, [isStreaming]);

  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
    setChatStarted(false);
  }, []);

  return {
    messages,
    isStreaming,
    error,
    sendMessage,
    clearChat,
    chatStarted,
  };
}
