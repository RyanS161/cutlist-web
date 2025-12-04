import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import { useChat } from '../hooks/useChat';
import { getDefaultSystemPrompt, executeCode, downloadProject, downloadCSV } from '../services/api';
import { CodePanel, type ExecutionResult } from './CodePanel';
import './ChatWindow.css';

// Custom markdown component renderers
const markdownComponents: Components = {
  // Custom image renderer with styling
  img: ({ src, alt }) => (
    <img 
      src={src} 
      alt={alt || ''} 
      className="chat-inline-image"
    />
  ),
  // Ensure code blocks have proper styling
  code: ({ className, children, ...props }) => {
    const isInline = !className;
    return isInline ? (
      <code className="inline-code" {...props}>{children}</code>
    ) : (
      <code className={className} {...props}>{children}</code>
    );
  },
  // Open links in new tab
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

/**
 * Component to render message content with markdown support.
 * Uses react-markdown for full markdown rendering including
 * headings, lists, code blocks, bold, italic, links, and images.
 */
function MessageContent({ content }: { content: string }) {
  return (
    <ReactMarkdown components={markdownComponents}>
      {content}
    </ReactMarkdown>
  );
}

/**
 * Chat window component with message display, code panel, and input.
 */
export function ChatWindow() {
  const [systemPrompt, setSystemPrompt] = useState('');
  const [isLoadingPrompt, setIsLoadingPrompt] = useState(true);
  const [designCode, setDesignCode] = useState('');
  const [executionResult, setExecutionResult] = useState<ExecutionResult>({ status: 'idle' });
  const [input, setInput] = useState('');
  
  // History state
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const designCodeRef = useRef(designCode);
  designCodeRef.current = designCode;
  
  // Add code to history
  const addToHistory = useCallback((code: string) => {
    setHistory(prev => {
      const newHistory = prev.slice(0, historyIndex + 1);
      // Only add if different from current head
      if (newHistory.length === 0 || newHistory[newHistory.length - 1] !== code) {
        newHistory.push(code);
        setHistoryIndex(newHistory.length - 1);
        return newHistory;
      }
      return prev;
    });
  }, [historyIndex]);

  // Execute code when it changes (from model or user save)
  const runCode = useCallback(async (code: string) => {
    if (!code.trim()) return;
    
    setExecutionResult({ status: 'running' });
    
    try {
      const result = await executeCode(code);
      setExecutionResult({
        status: result.success ? 'success' : 'error',
        output: result.output,
        error: result.error,
        result: result.result,
        stlUrl: result.stl_url,
        viewsUrl: result.views_url,
        assemblyGifUrl: result.assembly_gif_url,
      });
    } catch (err) {
      setExecutionResult({
        status: 'error',
        error: err instanceof Error ? err.message : 'Failed to execute code',
      });
    }
  }, []);
  
  // Callbacks for the chat hook
  const handleCodeUpdate = useCallback((code: string) => {
    setDesignCode(code);
  }, []);
  
  // Handle code change from user edits (save button)
  const handleUserCodeChange = useCallback((code: string) => {
    setDesignCode(code);
    addToHistory(code);
    runCode(code);
  }, [runCode, addToHistory]);
  
  const getCurrentCode = useCallback(() => {
    return designCodeRef.current;
  }, []);
  
  const { 
    messages, 
    isStreaming, 
    isReviewing, 
    isQAReviewing, 
    error, 
    sendMessage, 
    clearChat, 
    chatStarted 
  } = useChat({ 
    systemPrompt,
    onCodeUpdate: handleCodeUpdate,
    getCurrentCode,
  });
  
  // Track streaming state to save history and run code when done
  const prevStreamingRef = useRef(isStreaming);
  useEffect(() => {
    if (prevStreamingRef.current && !isStreaming && designCode) {
      // Streaming just finished
      addToHistory(designCode);
      runCode(designCode);
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming, designCode, addToHistory, runCode]);

  // History navigation
  const handleUndo = useCallback(() => {
    if (historyIndex > 0) {
      const newIndex = historyIndex - 1;
      setHistoryIndex(newIndex);
      const code = history[newIndex];
      setDesignCode(code);
      runCode(code);
    }
  }, [historyIndex, history, runCode]);

  const handleRedo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const newIndex = historyIndex + 1;
      setHistoryIndex(newIndex);
      const code = history[newIndex];
      setDesignCode(code);
      runCode(code);
    }
  }, [historyIndex, history, runCode]);

  // Load default system prompt on mount
  useEffect(() => {
    getDefaultSystemPrompt()
      .then(setSystemPrompt)
      .catch((err) => console.error('Failed to load system prompt:', err))
      .finally(() => setIsLoadingPrompt(false));
  }, []);

  // Track if user is near bottom of chat for smart auto-scroll
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);
  
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    
    // Consider "near bottom" if within 150px of the bottom
    const threshold = 150;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    isNearBottomRef.current = distanceFromBottom < threshold;
  }, []);

  // Auto-scroll to bottom when new messages arrive, but only if user is near bottom
  useEffect(() => {
    if (isNearBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Focus input on mount or when chat starts
  useEffect(() => {
    if (chatStarted) {
      inputRef.current?.focus();
    }
  }, [chatStarted]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;
    
    const message = input;
    setInput('');
    await sendMessage(message);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleClearChat = () => {
    clearChat();
    setDesignCode('');
    setExecutionResult({ status: 'idle' });
    // Reload default system prompt
    setIsLoadingPrompt(true);
    getDefaultSystemPrompt()
      .then(setSystemPrompt)
      .catch((err) => console.error('Failed to load system prompt:', err))
      .finally(() => setIsLoadingPrompt(false));
  };
  
  // Handle project download
  const handleDownloadProject = useCallback(async () => {
    try {
      await downloadProject({
        code: designCode,
        history: messages,
        stlUrl: executionResult.stlUrl,
        viewsUrl: executionResult.viewsUrl,
        assemblyGifUrl: executionResult.assemblyGifUrl,
      });
    } catch (err) {
      console.error('Failed to download project:', err);
      alert('Failed to download project. See console for details.');
    }
  }, [designCode, messages, executionResult]);

  // Handle CSV download
  const handleDownloadCSV = useCallback(async () => {
    try {
      await downloadCSV(designCode);
    } catch (err) {
      console.error('Failed to download CSV:', err);
      alert('Failed to download CSV. See console for details.');
    }
  }, [designCode]);

  return (
    <div className="app-container">
      <div className="chat-container">
        <div className="chat-header">
          <h1>Cutlist</h1>
          <button 
            onClick={handleClearChat} 
            className="clear-btn"
            disabled={isStreaming || isReviewing || isQAReviewing || (!chatStarted && messages.length === 0)}
          >
            {chatStarted ? 'New Chat' : 'Reset'}
          </button>
        </div>

        {!chatStarted ? (
          <div className="system-prompt-container">
            <div className="system-prompt-header">
              <h2>System Prompt</h2>
              <p className="system-prompt-hint">
                Customize the AI's behavior and personality before starting the chat.
                This cannot be changed once the conversation begins.
              </p>
            </div>
            <textarea
              className="system-prompt-input"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder={isLoadingPrompt ? 'Loading default prompt...' : 'Enter system prompt...'}
              disabled={isLoadingPrompt}
              rows={8}
            />
            <div className="system-prompt-footer">
              <span className="char-count">{systemPrompt.length} characters</span>
            </div>
          </div>
        ) : (
          <div 
            className="messages-container"
            ref={messagesContainerRef}
            onScroll={handleScroll}
          >
            {messages.map((message, index) => (
              <div
                key={index}
                className={`message ${message.role === 'user' ? 'user-message' : 'model-message'}${message.agentType === 'qa' ? ' qa-message' : ''}`}
              >
                <div className="message-role">
                  {message.role === 'user' ? 'You' : message.agentType === 'qa' ? 'QA Agent' : 'Designer Agent'}
                </div>
                <div className="message-content">
                  {message.content ? (
                    <MessageContent content={message.content} />
                  ) : (isStreaming && index === messages.length - 1 ? (
                    <span className="typing-indicator">●●●</span>
                  ) : null)}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}

        {error && (
          <div className="error-banner">
            <span>Error: {error}</span>
            <button onClick={() => window.location.reload()}>Retry</button>
          </div>
        )}

        <form onSubmit={handleSubmit} className="input-form">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={chatStarted 
              ? "Chat with the designer..."
              : "Describe what you want to build..."
            }
            disabled={isStreaming || isReviewing || isQAReviewing || isLoadingPrompt}
            rows={1}
            className="message-input"
          />
          <button 
            type="submit" 
            disabled={!input.trim() || isStreaming || isReviewing || isQAReviewing || isLoadingPrompt}
            className="send-btn"
          >
            {isStreaming ? 'Generating...' : isReviewing ? 'Reviewing...' : isQAReviewing ? 'QA Reviewing...' : chatStarted ? 'Send' : 'Start Design'}
          </button>
        </form>
        
        {!chatStarted && (
          <div className="quick-prompts">
            <span className="quick-prompts-label">Try:</span>
            <button 
              className="quick-prompt-btn"
              onClick={() => sendMessage("A chair with a slatted back")}
              disabled={isLoadingPrompt}
            >
              A chair with a slatted back
            </button>
            <button 
              className="quick-prompt-btn"
              onClick={() => sendMessage("A birdhouse")}
              disabled={isLoadingPrompt}
            >
              A birdhouse
            </button>
            <button 
              className="quick-prompt-btn"
              onClick={() => sendMessage("An open bookshelf with four shelves")}
              disabled={isLoadingPrompt}
            >
              An open bookshelf with four shelves
            </button>
            <button 
              className="quick-prompt-btn"
              onClick={() => sendMessage("The letters ETH")}
              disabled={isLoadingPrompt}
            >
              The letters ETH
            </button>
            <button 
              className="quick-prompt-btn"
              onClick={() => sendMessage("The letter T")}
              disabled={isLoadingPrompt}
            >
              The letter T
            </button>
          </div>
        )}
      </div>
      
      {chatStarted && (
        <CodePanel
          code={designCode}
          onCodeChange={handleUserCodeChange}
          isStreaming={isStreaming || isReviewing || isQAReviewing}
          executionResult={executionResult}
          onUndo={handleUndo}
          onRedo={handleRedo}
          canUndo={historyIndex > 0}
          canRedo={historyIndex < history.length - 1}
          onDownloadProject={handleDownloadProject}
          onDownloadCSV={handleDownloadCSV}
        />
      )}
    </div>
  );
}
