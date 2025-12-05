import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import { useChat, type AutoModeConfig } from '../hooks/useChat';
import { getDefaultSystemPrompt, executeCode, downloadProject, runTests, type TestSuiteResult } from '../services/api';
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
  
  // Auto mode state
  const [autoModeEnabled, setAutoModeEnabled] = useState(false);
  const [autoModeMaxIterations, setAutoModeMaxIterations] = useState(3);
  const [testResults, setTestResults] = useState<TestSuiteResult | null>(null);
  const [isRunningTests, setIsRunningTests] = useState(false);
  
  // Generation tracking state
  const [generationStartTime, setGenerationStartTime] = useState<number | null>(null);
  const [generationEndTime, setGenerationEndTime] = useState<number | null>(null);
  const [initialPrompt, setInitialPrompt] = useState<string>('');
  
  // History state
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const designCodeRef = useRef(designCode);
  designCodeRef.current = designCode;
  
  // Auto mode config
  const autoModeConfig: AutoModeConfig = {
    enabled: autoModeEnabled,
    maxIterations: autoModeMaxIterations,
  };
  
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
  
  // Callback when auto mode ends - capture generation end time
  const handleAutoModeEnd = useCallback(() => {
    setGenerationEndTime(Date.now());
  }, []);
  
  const { 
    messages, 
    isStreaming, 
    isReviewing, 
    isQAReviewing, 
    error, 
    sendMessage, 
    triggerQAReview, 
    clearChat, 
    chatStarted,
    autoModeIteration,
    autoModeActive,
    stopAutoMode,
    onExecutionComplete,
  } = useChat({ 
    systemPrompt,
    onCodeUpdate: handleCodeUpdate,
    getCurrentCode,
    autoModeConfig,
    onAutoModeEnd: handleAutoModeEnd,
  });
  
  // Run tests and call onExecutionComplete when done
  const runTestsAndNotify = useCallback(async (code: string, viewsUrl: string) => {
    if (isRunningTests) return;
    
    setIsRunningTests(true);
    try {
      const results = await runTests(code);
      setTestResults(results);
      
      // If auto mode is active, notify that execution is complete
      if (autoModeActive && viewsUrl) {
        // Format test results summary for QA agent
        const failedTestsDetails = results.tests
          .filter(t => t.status !== 'passed')
          .map(t => {
            let detail = `- ${t.name}: ${t.message || t.status}`;
            if (t.long_message) {
              detail += `\n  ${t.long_message.replace(/\n/g, '\n  ')}`;
            }
            return detail;
          })
          .join('\n\n');
        const summary = `Tests: ${results.passed} passed, ${results.failed} failed, ${results.errors} errors\n\n${failedTestsDetails ? `Failed Tests:\n${failedTestsDetails}` : 'All tests passed.'}`;
        
        onExecutionComplete({ viewsUrl, testResultsSummary: summary });
      } else if (!autoModeActive) {
        // Not in auto mode - capture end time when tests complete
        setGenerationEndTime(Date.now());
      }
    } catch (err) {
      console.error('Failed to run tests:', err);
      setTestResults({
        passed: 0,
        failed: 0,
        skipped: 0,
        errors: 1,
        tests: [{
          name: 'Assembly Test Suite',
          status: 'error',
          message: err instanceof Error ? err.message : 'Failed to run tests',
        }],
        success: false,
      });
    } finally {
      setIsRunningTests(false);
    }
  }, [isRunningTests, autoModeActive, onExecutionComplete]);
  
  // Track streaming state to save history and run code when done
  const prevStreamingRef = useRef(isStreaming);
  const executionResultRef = useRef(executionResult);
  executionResultRef.current = executionResult;
  
  useEffect(() => {
    if (prevStreamingRef.current && !isStreaming && designCode) {
      // Streaming just finished
      addToHistory(designCode);
      runCode(designCode);
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming, designCode, addToHistory, runCode]);
  
  // Track execution completion to run tests
  const prevExecutionStatus = useRef(executionResult?.status);
  useEffect(() => {
    // Run tests when execution transitions to success
    if (prevExecutionStatus.current !== 'success' && 
        executionResult?.status === 'success' && 
        designCode) {
      runTestsAndNotify(designCode, executionResult.viewsUrl || '');
    }
    prevExecutionStatus.current = executionResult?.status;
  }, [executionResult?.status, executionResult?.viewsUrl, designCode, runTestsAndNotify]);

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
    // Build detailed test information including long_message for agent
    const failedTestsDetails = testResults.tests
      .filter(test => test.status !== 'passed')
      .map(test => {
        let detail = `- **${test.name}**: ${test.message || ''}`;
        if (test.long_message) {
          detail += `\n${test.long_message}`;
        }
        return detail;
      })
      .join('\n\n');
    
    const message = `Please review these test results and fix any issues in the code:

**Test Results:**
- Passed: ${testResults.passed}
- Failed: ${testResults.failed}
- Errors: ${testResults.errors}

**Failed Tests:**
${failedTestsDetails || 'None'}

Please analyze the failures and update the code to fix them.`;
    
    sendMessage(message);
  }, [sendMessage]);

  // Handle error review request from output panel
  const handleReviewError = useCallback((error: string, _code: string) => {
    const message = `I got the following error when running the code:

\`\`\`
${error}
\`\`\`

Please analyze the error and update the code to fix it.`;
    
    sendMessage(message);
  }, [sendMessage]);

  // Handle QA review request from Actions panel
  const handleQAReview = useCallback((viewsUrl: string, testResultsSummary: string) => {
    triggerQAReview(viewsUrl, testResultsSummary);
  }, [triggerQAReview]);

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
    
    // Track generation start time and initial prompt on first message
    if (!chatStarted) {
      setGenerationStartTime(Date.now());
      setInitialPrompt(message);
    }
    
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
    setTestResults(null);
    setGenerationStartTime(null);
    setGenerationEndTime(null);
    setInitialPrompt('');
    // Reload default system prompt
    setIsLoadingPrompt(true);
    getDefaultSystemPrompt()
      .then(setSystemPrompt)
      .catch((err) => console.error('Failed to load system prompt:', err))
      .finally(() => setIsLoadingPrompt(false));
  };
  
  // Handle quick prompt click - also track generation time
  const handleQuickPrompt = useCallback((prompt: string) => {
    setGenerationStartTime(Date.now());
    setInitialPrompt(prompt);
    sendMessage(prompt);
  }, [sendMessage]);
  
  // Handle project download
  const handleDownloadProject = useCallback(async () => {
    try {
      // Calculate generation time in seconds (use captured end time, not current time)
      const endTime = generationEndTime || Date.now();
      const generationTime = generationStartTime 
        ? (endTime - generationStartTime) / 1000 
        : 0;
      
      await downloadProject({
        code: designCode,
        initialPrompt: initialPrompt,
        generationTime: generationTime,
        stlUrl: executionResult.stlUrl,
        viewsUrl: executionResult.viewsUrl,
        assemblyGifUrl: executionResult.assemblyGifUrl,
      });
    } catch (err) {
      console.error('Failed to download project:', err);
      alert('Failed to download project. See console for details.');
    }
  }, [designCode, initialPrompt, generationStartTime, generationEndTime, executionResult]);

  return (
    <div className="app-container">
      <div className="chat-container">
        <div className="chat-header">
          <h1>Cutlist</h1>
          {autoModeActive && (
            <div className="auto-mode-status">
              <span className="auto-mode-indicator">
                🔄 Auto Mode: Iteration {autoModeIteration + 1}/{autoModeMaxIterations}
              </span>
              <button 
                onClick={stopAutoMode}
                className="stop-auto-btn"
              >
                Stop
              </button>
            </div>
          )}
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
            
            {/* Auto Mode Settings */}
            <div className="auto-mode-settings">
              <div className="auto-mode-toggle">
                <label className="auto-mode-label">
                  <input
                    type="checkbox"
                    checked={autoModeEnabled}
                    onChange={(e) => setAutoModeEnabled(e.target.checked)}
                    disabled={isLoadingPrompt}
                  />
                  <span className="auto-mode-checkbox-label">Enable Auto Mode</span>
                </label>
                <p className="auto-mode-hint">
                  Automatically iterate: Designer → Execute → QA Review → Designer...
                </p>
              </div>
              {autoModeEnabled && (
                <div className="auto-mode-iterations">
                  <label>
                    Max Iterations:
                    <input
                      type="number"
                      min="1"
                      max="10"
                      value={autoModeMaxIterations}
                      onChange={(e) => setAutoModeMaxIterations(Math.max(1, Math.min(10, parseInt(e.target.value) || 1)))}
                      disabled={isLoadingPrompt}
                      className="iterations-input"
                    />
                  </label>
                </div>
              )}
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
              onClick={() => handleQuickPrompt("A chair with a slatted back")}
              disabled={isLoadingPrompt}
            >
              A chair with a slatted back
            </button>
            <button 
              className="quick-prompt-btn"
              onClick={() => handleQuickPrompt("A birdhouse")}
              disabled={isLoadingPrompt}
            >
              A birdhouse
            </button>
            <button 
              className="quick-prompt-btn"
              onClick={() => handleQuickPrompt("An open bookshelf with four shelves")}
              disabled={isLoadingPrompt}
            >
              An open bookshelf with four shelves
            </button>
            <button 
              className="quick-prompt-btn"
              onClick={() => handleQuickPrompt("The letters ETH")}
              disabled={isLoadingPrompt}
            >
              The letters ETH
            </button>
            <button 
              className="quick-prompt-btn"
              onClick={() => handleQuickPrompt("The letter T")}
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
          testResults={testResults}
          isRunningTests={isRunningTests}
          onReviewImage={handleReviewImage}
          onReviewTestResults={handleReviewTestResults}
          onReviewError={handleReviewError}
          onQAReview={handleQAReview}
          isReviewing={isReviewing}
          isQAReviewing={isQAReviewing}
          onUndo={handleUndo}
          onRedo={handleRedo}
          canUndo={historyIndex > 0}
          canRedo={historyIndex < history.length - 1}
          onDownloadProject={handleDownloadProject}
        />
      )}
    </div>
  );
}
