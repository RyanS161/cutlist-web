import { useState, useRef, useEffect, useCallback } from 'react';
import { useChat } from '../hooks/useChat';
import { getDefaultSystemPrompt, executeCode, type TestSuiteResult } from '../services/api';
import { CodePanel, type ExecutionResult } from './CodePanel';
import './ChatWindow.css';

/**
 * Component to render message content with support for markdown images.
 * Parses ![alt](url) syntax and renders as <img> tags.
 */
function MessageContent({ content }: { content: string }) {
  // Regex to match markdown images: ![alt text](url)
  const imageRegex = /!\[([^\]]*)\]\(([^)]+)\)/g;
  
  const parts: (string | { type: 'image'; alt: string; url: string })[] = [];
  let lastIndex = 0;
  let match;
  
  while ((match = imageRegex.exec(content)) !== null) {
    // Add text before the image
    if (match.index > lastIndex) {
      parts.push(content.slice(lastIndex, match.index));
    }
    // Add the image
    parts.push({ type: 'image', alt: match[1], url: match[2] });
    lastIndex = match.index + match[0].length;
  }
  
  // Add remaining text after last image
  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }
  
  return (
    <>
      {parts.map((part, i) => {
        if (typeof part === 'string') {
          return <span key={i}>{part}</span>;
        } else {
          return (
            <img 
              key={i}
              src={part.url} 
              alt={part.alt} 
              className="chat-inline-image"
            />
          );
        }
      })}
    </>
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

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const designCodeRef = useRef(designCode);
  designCodeRef.current = designCode;
  
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
    runCode(code);
  }, [runCode]);
  
  const getCurrentCode = useCallback(() => {
    return designCodeRef.current;
  }, []);
  
  const { messages, isStreaming, isReviewing, error, sendMessage, clearChat, chatStarted } = useChat({ 
    systemPrompt,
    onCodeUpdate: handleCodeUpdate,
    getCurrentCode,
  });
  
  // Handle image review request from Actions panel
  const handleReviewImage = useCallback((viewsUrl: string, _code: string) => {
    // Send as a user message asking for visual review, include the image
    const message = `Please review the rendered image of my design:

![Design Preview](${viewsUrl})

Check if:
- The proportions and structure look correct
- All parts appear to be properly positioned and aligned
- The design matches what I requested
- There are any visual issues or improvements to suggest

If you see any problems, please update the code to fix them.`;
    
    sendMessage(message);
  }, [sendMessage]);
  
  // Handle test results review request from Actions panel
  const handleReviewTestResults = useCallback((testResults: TestSuiteResult, _code: string) => {
    // Format test results as a message for the AI
    const testSummary = testResults.tests.map(test => 
      `- ${test.name}: ${test.status.toUpperCase()}${test.message ? ` - ${test.message}` : ''}`
    ).join('\n');
    
    const message = `Please review these test results and fix any issues in the code:

**Test Results:**
- Passed: ${testResults.passed}
- Failed: ${testResults.failed}
- Errors: ${testResults.errors}

**Details:**
${testSummary}

Please analyze the failures and update the code to fix them.`;
    
    sendMessage(message);
  }, [sendMessage]);

  // Handle error review request from output panel
  const handleReviewError = useCallback((error: string, _code: string) => {
    const message = `I got the following error when running the code. Please fix it:

\`\`\`
${error}
\`\`\`

Please analyze the error and update the code to fix it.`;
    
    sendMessage(message);
  }, [sendMessage]);

  // Load default system prompt on mount
  useEffect(() => {
    getDefaultSystemPrompt()
      .then(setSystemPrompt)
      .catch((err) => console.error('Failed to load system prompt:', err))
      .finally(() => setIsLoadingPrompt(false));
  }, []);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
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
  
  // Run code when streaming completes and there's new code
  const prevStreamingRef = useRef(isStreaming);
  useEffect(() => {
    // Detect when streaming just finished
    if (prevStreamingRef.current && !isStreaming && designCode) {
      runCode(designCode);
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming, designCode, runCode]);

  return (
    <div className="app-container">
      <div className="chat-container">
        <div className="chat-header">
          <h1>Woodworking Designer</h1>
          <button 
            onClick={handleClearChat} 
            className="clear-btn"
            disabled={isStreaming || isReviewing || (!chatStarted && messages.length === 0)}
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
          <div className="messages-container">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`message ${message.role === 'user' ? 'user-message' : 'model-message'}`}
              >
                <div className="message-role">
                  {message.role === 'user' ? 'You' : 'AI'}
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
              ? "Describe your woodworking design... (Enter to send)"
              : "Describe what you want to build..."
            }
            disabled={isStreaming || isReviewing || isLoadingPrompt}
            rows={1}
            className="message-input"
          />
          <button 
            type="submit" 
            disabled={!input.trim() || isStreaming || isReviewing || isLoadingPrompt}
            className="send-btn"
          >
            {isStreaming ? 'Generating...' : isReviewing ? 'Reviewing...' : chatStarted ? 'Send' : 'Start Design'}
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
          </div>
        )}
      </div>
      
      {chatStarted && (
        <CodePanel
          code={designCode}
          onCodeChange={handleUserCodeChange}
          isStreaming={isStreaming || isReviewing}
          executionResult={executionResult}
          onReviewImage={handleReviewImage}
          onReviewTestResults={handleReviewTestResults}
          onReviewError={handleReviewError}
          isReviewing={isReviewing}
        />
      )}
    </div>
  );
}
