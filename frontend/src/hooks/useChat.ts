import { useState, useCallback, useRef } from 'react';
import type { Message } from '../services/api';
import { streamChat, streamQAReview } from '../services/api';

// Extended message type to support QA agent
export interface ExtendedMessage extends Message {
  agentType?: 'designer' | 'qa';
}

// Code block markers (markdown style)
const CODE_START_PATTERN = /```python\n?/;
const CODE_END_MARKER = '```';

// Auto mode configuration
export interface AutoModeConfig {
  enabled: boolean;
  maxIterations: number;
}

interface UseChatOptions {
  systemPrompt?: string;
  onCodeUpdate?: (code: string) => void;
  getCurrentCode?: () => string;
  autoModeConfig?: AutoModeConfig;
  onExecutionNeeded?: () => void;
  onAutoModeEnd?: () => void;
}

// Callback type for execution completion
export interface ExecutionCompletionData {
  viewsUrl: string;
  testResultsSummary: string;
}

interface UseChatReturn {
  messages: ExtendedMessage[];
  isStreaming: boolean;
  isReviewing: boolean;
  isQAReviewing: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  triggerQAReview: (viewsUrl: string, testResultsSummary: string) => Promise<void>;
  clearChat: () => void;
  chatStarted: boolean;
  // Auto mode
  autoModeIteration: number;
  autoModeActive: boolean;
  stopAutoMode: () => void;
  onExecutionComplete: (data: ExecutionCompletionData) => void;
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
  const [messages, setMessages] = useState<ExtendedMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isReviewing] = useState(false);
  const [isQAReviewing, setIsQAReviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatStarted, setChatStarted] = useState(false);
  
  // Auto mode state
  const [autoModeIteration, setAutoModeIteration] = useState(0);
  const [autoModeActive, setAutoModeActive] = useState(false);
  const autoModeStoppedRef = useRef(false);
  
  // Use ref to track current messages during streaming
  const messagesRef = useRef<ExtendedMessage[]>([]);
  messagesRef.current = messages;
  
  // Store the system prompt for this chat session
  const systemPromptRef = useRef<string | undefined>(options.systemPrompt);
  systemPromptRef.current = options.systemPrompt;
  
  // Store auto mode config
  const autoModeConfigRef = useRef(options.autoModeConfig);
  autoModeConfigRef.current = options.autoModeConfig;
  
  // Store callbacks
  const onCodeUpdateRef = useRef(options.onCodeUpdate);
  onCodeUpdateRef.current = options.onCodeUpdate;
  
  const getCurrentCodeRef = useRef(options.getCurrentCode);
  getCurrentCodeRef.current = options.getCurrentCode;
  
  const onAutoModeEndRef = useRef(options.onAutoModeEnd);
  onAutoModeEndRef.current = options.onAutoModeEnd;
  
  // Track raw content for code extraction
  const rawContentRef = useRef('');

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isStreaming) return;

    setError(null);
    setChatStarted(true);
    rawContentRef.current = '';
    
    // Start auto mode if enabled and this is a fresh start
    if (autoModeConfigRef.current?.enabled && !autoModeActive) {
      setAutoModeActive(true);
      setAutoModeIteration(0);
      autoModeStoppedRef.current = false;
    }
    
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
  }, [isStreaming, autoModeActive]);

  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
    setChatStarted(false);
    setAutoModeIteration(0);
    setAutoModeActive(false);
    autoModeStoppedRef.current = false;
    rawContentRef.current = '';
  }, []);

  /**
   * Stop auto mode iteration loop.
   */
  const stopAutoMode = useCallback(() => {
    autoModeStoppedRef.current = true;
    setAutoModeActive(false);
    setAutoModeIteration(0);
    onAutoModeEndRef.current?.();
  }, []);

  /**
   * Trigger a QA review by sending the design to a fresh QA agent.
   * The QA agent will analyze the image and test results, providing independent feedback.
   * After the QA review completes, the feedback is automatically sent to the Designer Agent.
   * Returns true if QA passed, false otherwise.
   */
  const triggerQAReviewInternal = useCallback(async (viewsUrl: string, testResultsSummary: string): Promise<boolean> => {
    return new Promise((resolve) => {
      if (isStreaming || isReviewing || isQAReviewing) {
        resolve(false);
        return;
      }

      setError(null);
      setIsQAReviewing(true);
      rawContentRef.current = '';

      // Extract only user messages for context
      const userMessages = messagesRef.current
        .filter(msg => msg.role === 'user')
        .map(msg => msg.content);

      // Add a QA agent message to show review is in progress
      const qaMessage: ExtendedMessage = { 
        role: 'model', 
        content: '🔍 **QA Agent reviewing design...**',
        agentType: 'qa'
      };
      setMessages((prev) => [...prev, qaMessage]);

      let qaFeedback = '';

      streamQAReview({
        viewsUrl,
        testResultsSummary,
        userMessages,
        onChunk: (chunk: string) => {
          // Accumulate raw content
          rawContentRef.current += chunk;
          qaFeedback = rawContentRef.current.trim();

          // QA agent shouldn't provide code, so just use raw content
          const displayText = qaFeedback;

          // Update the QA message with content
          setMessages((prev) => {
            const updated = [...prev];
            const lastIdx = updated.length - 1;
            if (updated[lastIdx]?.role === 'model' && updated[lastIdx]?.agentType === 'qa') {
              updated[lastIdx] = {
                ...updated[lastIdx],
                content: displayText,
              };
            }
            return updated;
          });
        },
        onError: (err: Error) => {
          setError(err.message);
          setIsQAReviewing(false);
          resolve(false);
        },
        onComplete: async () => {
          setIsQAReviewing(false);
          
          // Check if QA passed
          const qaPassed = qaFeedback.includes('QA_PASSED') || qaFeedback.includes('QA PASSED');
          
          if (qaPassed) {
            resolve(true);
            return;
          }
          
          // Automatically send QA feedback to the Designer Agent
          if (qaFeedback) {
            // Small delay to ensure UI updates before starting designer response
            await new Promise(r => setTimeout(r, 100));
            
            // Simple prompt for the designer to act on the QA feedback
            const designerPrompt = "Please address the QA Agent's feedback and update the code.";
            
            // Get current code to send with the message
            let currentCode = getCurrentCodeRef.current?.();
            if (currentCode) {
              currentCode = currentCode
                .replace(/<[^>]*>/g, '')
                .replace(/&lt;/g, '<')
                .replace(/&gt;/g, '>')
                .replace(/&amp;/g, '&')
                .replace(/&quot;/g, '"');
            }

            // Build history including the QA agent message with qa_agent role
            // The backend will convert qa_agent messages appropriately
            const historyWithQA = [
              ...messagesRef.current.filter(m => m.role !== 'model' || m.agentType !== 'qa').map(m => ({
                role: m.role as 'user' | 'model' | 'qa_agent',
                content: m.content
              })),
              { role: 'qa_agent' as const, content: qaFeedback }
            ];
            
            // Add placeholder for assistant response (no user message shown)
            const assistantMessage: ExtendedMessage = { role: 'model', content: '' };
            setMessages((prev) => [...prev, assistantMessage]);
            
            setIsStreaming(true);
            rawContentRef.current = '';

            streamChat({
              message: designerPrompt,
              history: historyWithQA,
              systemPrompt: systemPromptRef.current,
              currentCode,
              onChunk: (chunk: string) => {
                rawContentRef.current += chunk;
                const { displayText, code } = parseStreamContent(rawContentRef.current);
                
                if (code !== null && onCodeUpdateRef.current) {
                  const cleanCode = code
                    .replace(/<[^>]*>/g, '')
                    .replace(/&lt;/g, '<')
                    .replace(/&gt;/g, '>')
                    .replace(/&amp;/g, '&')
                    .replace(/&quot;/g, '"');
                  onCodeUpdateRef.current(cleanCode);
                }
                
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (updated[lastIdx]?.role === 'model' && !updated[lastIdx]?.agentType) {
                    updated[lastIdx] = { ...updated[lastIdx], content: displayText };
                  }
                  return updated;
                });
              },
              onError: (err: Error) => {
                setError(err.message);
                setIsStreaming(false);
                resolve(false);
              },
              onComplete: () => {
                setIsStreaming(false);
                resolve(false);
              },
            });
          } else {
            resolve(false);
          }
        },
      });
    });
  }, [isStreaming, isReviewing, isQAReviewing]);

  /**
   * Public wrapper for triggerQAReview that doesn't return a promise result.
   */
  const triggerQAReview = useCallback(async (viewsUrl: string, testResultsSummary: string) => {
    await triggerQAReviewInternal(viewsUrl, testResultsSummary);
  }, [triggerQAReviewInternal]);

  /**
   * Callback to be called when execution and tests complete.
   * This is the explicit signal that auto mode waits for.
   */
  const onExecutionComplete = useCallback(async (data: ExecutionCompletionData) => {
    // Only proceed if auto mode is active and not stopped
    if (!autoModeConfigRef.current?.enabled || !autoModeActive || autoModeStoppedRef.current) {
      return;
    }

    const { viewsUrl, testResultsSummary } = data;
    
    // Trigger QA review and check if passed
    const qaPassed = await triggerQAReviewInternal(viewsUrl, testResultsSummary);
    
    if (qaPassed || autoModeStoppedRef.current) {
      // QA passed or stopped - end auto mode
      setAutoModeActive(false);
      setAutoModeIteration(0);
      onAutoModeEndRef.current?.();
      return;
    }
    
    // Increment iteration
    setAutoModeIteration(prev => {
      const next = prev + 1;
      const maxIterations = autoModeConfigRef.current?.maxIterations || 3;
      
      if (next >= maxIterations) {
        // Reached max iterations - end auto mode
        setAutoModeActive(false);
        onAutoModeEndRef.current?.();
        return 0;
      }
      
      return next;
    });
    
    // The designer agent has already responded (in triggerQAReviewInternal)
    // The execution/test will happen automatically via the existing useEffect in ChatWindow
    // which will call onExecutionComplete again when ready
  }, [autoModeActive, triggerQAReviewInternal]);

  return {
    messages,
    isStreaming,
    isReviewing,
    isQAReviewing,
    error,
    sendMessage,
    triggerQAReview,
    clearChat,
    chatStarted,
    // Auto mode
    autoModeIteration,
    autoModeActive,
    stopAutoMode,
    onExecutionComplete,
  };
}
