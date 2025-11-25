import React, { useState, useRef, useEffect } from 'react';
import { useChat } from '../hooks/useChat';
import { getDefaultSystemPrompt } from '../services/api';
import './ChatWindow.css';

/**
 * Chat window component with message display and input.
 */
export function ChatWindow() {
  const [systemPrompt, setSystemPrompt] = useState('');
  const [isLoadingPrompt, setIsLoadingPrompt] = useState(true);
  const { messages, isStreaming, error, sendMessage, clearChat, chatStarted } = useChat({ systemPrompt });
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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
    // Reload default system prompt
    setIsLoadingPrompt(true);
    getDefaultSystemPrompt()
      .then(setSystemPrompt)
      .catch((err) => console.error('Failed to load system prompt:', err))
      .finally(() => setIsLoadingPrompt(false));
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h1>Gemini Chat</h1>
        <button 
          onClick={handleClearChat} 
          className="clear-btn"
          disabled={isStreaming || (!chatStarted && messages.length === 0)}
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
                {message.role === 'user' ? 'You' : 'Gemini'}
              </div>
              <div className="message-content">
                {message.content || (isStreaming && index === messages.length - 1 ? (
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
            ? "Type a message... (Enter to send, Shift+Enter for new line)"
            : "Type your first message to start the chat..."
          }
          disabled={isStreaming || isLoadingPrompt}
          rows={1}
          className="message-input"
        />
        <button 
          type="submit" 
          disabled={!input.trim() || isStreaming || isLoadingPrompt}
          className="send-btn"
        >
          {isStreaming ? 'Sending...' : chatStarted ? 'Send' : 'Start Chat'}
        </button>
      </form>
    </div>
  );
}
