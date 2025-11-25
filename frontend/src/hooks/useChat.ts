import { useState, useCallback, useRef } from 'react';
import type { Message } from '../services/api';
import { streamChat } from '../services/api';

// Code block markers (markdown style)
const CODE_START_PATTERN = /```python\n?/;
const CODE_END_MARKER = '```';

interface UseChatOptions {
  systemPrompt?: string;
  onCodeUpdate?: (code: string) => void;
  getCurrentCode?: () => string;
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
 * Parse streaming content to extract code blocks and clean message text.
 * Uses markdown-style ```python code blocks.
 * Returns the cleaned text and any extracted code.
 */
function parseStreamContent(fullContent: string): { displayText: string; code: string | null } {
  let displayText = fullContent;
  let code: string | null = null;
  
  // Find markdown code block: ```python ... ```
  const startMatch = fullContent.match(CODE_START_PATTERN);
  
  if (startMatch && startMatch.index !== undefined) {
    const startIdx = startMatch.index;
    const codeStartIdx = startIdx + startMatch[0].length;
    
    // Look for closing ``` after the opening
    const remainingContent = fullContent.slice(codeStartIdx);
    const endIdx = remainingContent.indexOf(CODE_END_MARKER);
    
    if (endIdx !== -1) {
      // Complete code block found
      code = remainingContent.slice(0, endIdx).trim();
      // Remove the code block from display text
      const fullEndIdx = codeStartIdx + endIdx + CODE_END_MARKER.length;
      displayText = fullContent.slice(0, startIdx) + fullContent.slice(fullEndIdx);
    } else {
      // Partial code block (still streaming)
      code = remainingContent.trim();
      displayText = fullContent.slice(0, startIdx);
    }
  }
  
  // Clean up display text
  displayText = displayText.trim();
  
  return { displayText, code };
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
  
  // Store callbacks
  const onCodeUpdateRef = useRef(options.onCodeUpdate);
  onCodeUpdateRef.current = options.onCodeUpdate;
  
  const getCurrentCodeRef = useRef(options.getCurrentCode);
  getCurrentCodeRef.current = options.getCurrentCode;
  
  // Track raw content for code extraction
  const rawContentRef = useRef('');

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isStreaming) return;

    setError(null);
    setChatStarted(true);
    rawContentRef.current = '';
    
    // Add user message
    const userMessage: Message = { role: 'user', content: content.trim() };
    const updatedMessages = [...messagesRef.current, userMessage];
    setMessages(updatedMessages);
    
    // Add placeholder for assistant response
    const assistantMessage: Message = { role: 'model', content: '' };
    setMessages([...updatedMessages, assistantMessage]);
    
    setIsStreaming(true);
    
    // Get current code to send with the message
    // Strip any HTML that might have leaked in
    let currentCode = getCurrentCodeRef.current?.();
    if (currentCode) {
      currentCode = currentCode
        .replace(/<[^>]*>/g, '')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')
        .replace(/&quot;/g, '"');
    }

    await streamChat({
      message: content.trim(),
      history: updatedMessages.slice(0, -1), // Don't include the message we just added
      systemPrompt: systemPromptRef.current,
      currentCode,
      onChunk: (chunk) => {
        // Accumulate raw content
        rawContentRef.current += chunk;
        
        // Parse the content
        const { displayText, code } = parseStreamContent(rawContentRef.current);
        
        // Update code panel if we have code
        // Strip any HTML that might have leaked in (safety measure)
        if (code !== null && onCodeUpdateRef.current) {
          const cleanCode = code
            .replace(/<[^>]*>/g, '')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .replace(/&amp;/g, '&')
            .replace(/&quot;/g, '"');
          onCodeUpdateRef.current(cleanCode);
        }
        
        // Update message with cleaned display text
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (updated[lastIdx]?.role === 'model') {
            updated[lastIdx] = {
              ...updated[lastIdx],
              content: displayText,
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
    rawContentRef.current = '';
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
