import { useState, useEffect } from 'react';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import 'highlight.js/styles/github-dark.css';
import './CodePanel.css';

// Register Python language
hljs.registerLanguage('python', python);

interface CodePanelProps {
  code: string;
  onCodeChange: (code: string) => void;
  isStreaming: boolean;
}

/**
 * Code panel component with Python syntax highlighting and edit mode.
 * Uses a simple CSS-based highlighting approach to avoid extra dependencies.
 */
export function CodePanel({ code, onCodeChange, isStreaming }: CodePanelProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedCode, setEditedCode] = useState(code);
  const [copied, setCopied] = useState(false);

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

  return (
    <div className="code-panel">
      <div className="code-panel-header">
        <h3>Design Code</h3>
        <div className="code-panel-actions">
          {isEditing ? (
            <>
              <button onClick={handleSave} className="code-btn save-btn">
                Save
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
    </div>
  );
}
