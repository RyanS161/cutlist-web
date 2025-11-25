import { useState, useEffect } from 'react';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import 'highlight.js/styles/github-dark.css';
import './CodePanel.css';

// Register Python language
hljs.registerLanguage('python', python);

export type ExecutionStatus = 'idle' | 'running' | 'success' | 'error';

export interface ExecutionResult {
  status: ExecutionStatus;
  output?: string;
  error?: string;
  result?: string;
}

interface CodePanelProps {
  code: string;
  onCodeChange: (code: string) => void;
  isStreaming: boolean;
  executionResult?: ExecutionResult;
}

/**
 * Code panel component with Python syntax highlighting and edit mode.
 * Uses highlight.js for syntax highlighting.
 */
export function CodePanel({ code, onCodeChange, isStreaming, executionResult }: CodePanelProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedCode, setEditedCode] = useState(code);
  const [copied, setCopied] = useState(false);
  const [showOutput, setShowOutput] = useState(false);

  // Sync edited code with incoming code when not editing
  useEffect(() => {
    if (!isEditing) {
      setEditedCode(code);
    }
  }, [code, isEditing]);

  const handleEdit = () => {
    setIsEditing(true);
    setEditedCode(code);
  };

  const handleSave = () => {
    onCodeChange(editedCode);
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditedCode(code);
    setIsEditing(false);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  // Python syntax highlighting using highlight.js
  const highlightPython = (codeInput: string): string => {
    if (!codeInput) return '';
    
    // Strip any HTML that might have been accidentally included
    const cleanCode = codeInput
      .replace(/<[^>]*>/g, '')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&')
      .replace(/&quot;/g, '"');
    
    try {
      const result = hljs.highlight(cleanCode, { language: 'python' });
      return result.value;
    } catch {
      // Fallback to escaped plain text if highlighting fails
      return cleanCode
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }
  };

  const getStatusIcon = () => {
    switch (executionResult?.status) {
      case 'running':
        return <span className="status-icon running">⟳</span>;
      case 'success':
        return <span className="status-icon success">✓</span>;
      case 'error':
        return <span className="status-icon error">✗</span>;
      default:
        return null;
    }
  };

  const getStatusText = () => {
    switch (executionResult?.status) {
      case 'running':
        return 'Running...';
      case 'success':
        return 'Success';
      case 'error':
        return 'Error';
      default:
        return '';
    }
  };

  // Check if there's any output to show
  const hasOutput = executionResult && (
    executionResult.status === 'running' ||
    executionResult.error ||
    executionResult.output ||
    executionResult.result
  );

  return (
    <div className="code-panel">
      <div className="code-panel-header">
        <div className="code-panel-title">
          <h3>Design Code</h3>
          {executionResult && executionResult.status !== 'idle' && (
            <div className={`execution-status ${executionResult.status}`}>
              {getStatusIcon()}
              <span>{getStatusText()}</span>
            </div>
          )}
        </div>
        <div className="code-panel-actions">
          {isEditing ? (
            <>
              <button onClick={handleSave} className="code-btn save-btn">
                Save & Run
              </button>
              <button onClick={handleCancel} className="code-btn cancel-btn">
                Cancel
              </button>
            </>
          ) : (
            <>
              <button 
                onClick={handleEdit} 
                className="code-btn edit-btn"
                disabled={isStreaming || !code}
              >
                Edit
              </button>
              <button 
                onClick={handleCopy} 
                className="code-btn copy-btn"
                disabled={!code}
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </>
          )}
        </div>
      </div>
      
      <div className="code-panel-body">
        <div className="code-panel-content">
          {code || isEditing ? (
            <div className="code-editor-container">
              <pre className="code-display">
                <code 
                  className="language-python"
                  dangerouslySetInnerHTML={{ __html: highlightPython(isEditing ? editedCode : code) }}
                />
              </pre>
              {isEditing && (
                <textarea
                  className="code-editor-overlay"
                  value={editedCode}
                  onChange={(e) => setEditedCode(e.target.value)}
                  spellCheck={false}
                  autoFocus
                />
              )}
            </div>
          ) : (
            <div className="code-empty">
              <p>No design code yet.</p>
              <p className="code-hint">
                The AI will generate Python code here when you describe your design.
              </p>
            </div>
          )}
          
          {isStreaming && (
            <div className="code-streaming-indicator">
              <span className="streaming-dot">●</span> Generating...
            </div>
          )}
        </div>
        
        {/* Output Panel - Always visible when there's output */}
        {hasOutput && (
          <div className={`output-panel ${executionResult?.status === 'error' ? 'has-error' : ''}`}>
            <div className="output-panel-header">
              <div className="output-panel-title">
                {executionResult?.status === 'error' && <span className="output-icon error">⚠</span>}
                {executionResult?.status === 'success' && <span className="output-icon success">✓</span>}
                {executionResult?.status === 'running' && <span className="output-icon running">⟳</span>}
                <span>Output</span>
              </div>
              {executionResult?.status !== 'running' && (
                <button onClick={() => setShowOutput(!showOutput)} className="toggle-output-btn">
                  {showOutput ? '▼' : '▲'}
                </button>
              )}
            </div>
            {(showOutput || executionResult?.status === 'running' || executionResult?.status === 'error') && (
              <div className="output-panel-content">
                {executionResult?.status === 'running' ? (
                  <div className="output-running">
                    <span className="running-spinner">⟳</span>
                    <span>Executing code...</span>
                  </div>
                ) : executionResult?.error ? (
                  <pre className="output-error">{executionResult.error}</pre>
                ) : (
                  <>
                    {executionResult?.output && (
                      <pre className="output-stdout">{executionResult.output}</pre>
                    )}
                    {executionResult?.result && (
                      <div className="output-result">
                        <span className="result-label">Result:</span>
                        <pre>{executionResult.result}</pre>
                      </div>
                    )}
                    {!executionResult?.output && !executionResult?.result && (
                      <p className="output-empty">Code executed successfully with no output</p>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
