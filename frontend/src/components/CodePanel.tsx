import { useState, useEffect, useRef, lazy, Suspense } from 'react';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import 'highlight.js/styles/github-dark.css';
import './CodePanel.css';
import { ActionsPanel } from './ActionsPanel';

// Lazy load the heavy Three.js STL viewer
const StlViewer = lazy(() => import('./StlViewer'));

// Loading fallback for the 3D viewer
function StlViewerLoading() {
  return (
    <div className="stl-viewer-loading">
      <span className="loading-spinner">⟳</span>
      <span>Loading 3D viewer...</span>
    </div>
  );
}

// Register Python language
hljs.registerLanguage('python', python);

export type ExecutionStatus = 'idle' | 'running' | 'success' | 'error';

export interface ExecutionResult {
  status: ExecutionStatus;
  output?: string;
  error?: string;
  result?: string;
  stlUrl?: string;
  viewsUrl?: string;
  assemblyGifUrl?: string;
}

interface CodePanelProps {
  code: string;
  onCodeChange: (code: string) => void;
  isStreaming: boolean;
  executionResult?: ExecutionResult;
  onReviewError?: (error: string, code: string) => void;
  onDownloadProject?: () => void;
  onDownloadCSV?: () => void;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
}

/**
 * Code panel component with Python syntax highlighting and edit mode.
 * Uses highlight.js for syntax highlighting.
 */
export function CodePanel({ 
  code, 
  onCodeChange, 
  isStreaming, 
  executionResult,
  onReviewError,
  onDownloadProject,
  onDownloadCSV,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
}: CodePanelProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedCode, setEditedCode] = useState(code);
  const [copied, setCopied] = useState(false);
  const [showOutput, setShowOutput] = useState(false);
  const [isCodeUpdating, setIsCodeUpdating] = useState(false);
  
  // Track if code is actively being updated during streaming
  const prevCodeRef = useRef(code);
  useEffect(() => {
    if (isStreaming && code !== prevCodeRef.current) {
      // Code changed while streaming - show generating indicator
      setIsCodeUpdating(true);
    } else if (!isStreaming) {
      // Streaming stopped - hide generating indicator
      setIsCodeUpdating(false);
    }
    prevCodeRef.current = code;
  }, [code, isStreaming]);

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
    if (isCodeUpdating) {
      return <span className="status-icon streaming">●</span>;
    }
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
    if (isCodeUpdating) {
      return 'Generating...';
    }
    switch (executionResult?.status) {
      case 'running':
        return 'Executing...';
      case 'success':
        return 'Executed';
      case 'error':
        return 'Error';
      default:
        return '';
    }
  };

  const getStatusClass = () => {
    if (isCodeUpdating) return 'streaming';
    return executionResult?.status || '';
  };

  // Check if there's any output to show
  const hasOutput = executionResult && (
    executionResult.status === 'running' ||
    executionResult.error ||
    executionResult.output ||
    executionResult.result ||
    executionResult.stlUrl ||
    executionResult.viewsUrl
  );

  return (
    <div className="code-panel">
      <div className="code-panel-header">
        <div className="code-panel-title">
          <h3>Design Code</h3>
          {(isCodeUpdating || (executionResult && executionResult.status !== 'idle')) && (
            <div className={`execution-status ${getStatusClass()}`}>
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
              <div className="history-controls">
                <button 
                  onClick={onUndo} 
                  className="code-btn history-btn"
                  disabled={!canUndo || isStreaming}
                  title="Previous Version"
                >
                  ←
                </button>
                <button 
                  onClick={onRedo} 
                  className="code-btn history-btn"
                  disabled={!canRedo || isStreaming}
                  title="Next Version"
                >
                  →
                </button>
              </div>
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
                The designer agent will generate Python code here when you describe your design.
              </p>
            </div>
          )}
        </div>
        
        {/* Output Panel - Always visible when there's output */}
        {hasOutput && (
          <div className={`output-panel ${executionResult?.status === 'error' ? 'has-error' : ''} ${executionResult?.stlUrl ? 'has-stl' : ''}`}>
            <div className="output-panel-header">
              <div className="output-panel-title">
                {executionResult?.status === 'error' && <span className="output-icon error">⚠</span>}
                {executionResult?.status === 'success' && <span className="output-icon success">✓</span>}
                {executionResult?.status === 'running' && <span className="output-icon running">⟳</span>}
                <span>{executionResult?.stlUrl ? '3D Preview' : 'Output'}</span>
              </div>
              {executionResult?.status !== 'running' && (
                <button onClick={() => setShowOutput(!showOutput)} className="toggle-output-btn">
                  {showOutput ? '▼' : '▲'}
                </button>
              )}
            </div>
            {(showOutput || executionResult?.status === 'running' || executionResult?.status === 'error' || executionResult?.stlUrl) && (
              <div className="output-panel-content">
                {executionResult?.status === 'running' ? (
                  <div className="output-running">
                    <span className="running-spinner">⟳</span>
                    <span>Executing code...</span>
                  </div>
                ) : executionResult?.error ? (
                  <div className="error-container">
                    <pre className="output-error">{executionResult.error}</pre>
                  </div>
                ) : (
                  <>
                    {/* STL 3D Viewer and rendered views side by side */}
                    {executionResult?.stlUrl && (
                      <div className="model-viewers-container">
                        <div className="stl-viewer-container">
                          <div className="viewer-label">
                            <span>Interactive 3D View</span>
                            <a 
                              href={executionResult.stlUrl} 
                              download="model.stl"
                              className="download-stl-btn"
                              title="Download STL file"
                            >
                              ⬇ Download STL
                            </a>
                          </div>
                          <Suspense fallback={<StlViewerLoading />}>
                            <StlViewer url={executionResult.stlUrl} />
                          </Suspense>
                        </div>
                        {executionResult?.viewsUrl && (
                          <div className="views-container">
                            <div className="viewer-label">Rendered Views</div>
                            <img 
                              src={executionResult.viewsUrl} 
                              alt="Model views from 4 angles" 
                              className="combined-views-image"
                            />
                          </div>
                        )}
                        {executionResult?.assemblyGifUrl && (
                          <div className="views-container">
                            <div className="viewer-label">Assembly Animation</div>
                            <img 
                              src={executionResult.assemblyGifUrl} 
                              alt="Assembly animation showing parts being added" 
                              className="assembly-gif-image"
                            />
                          </div>
                        )}
                      </div>
                    )}
                    {executionResult?.output && (
                      <pre className="output-stdout">{executionResult.output}</pre>
                    )}
                    {executionResult?.result && !executionResult?.stlUrl && (
                      <div className="output-result">
                        <span className="result-label">Result:</span>
                        <pre>{executionResult.result}</pre>
                      </div>
                    )}
                    {!executionResult?.output && !executionResult?.result && !executionResult?.stlUrl && (
                      <p className="output-empty">Code executed successfully with no output</p>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}
        
        {/* Bottom Section: Actions panel */}
        <div className="bottom-panels-container">
          <ActionsPanel
            onDownloadProject={() => onDownloadProject?.()}
            onDownloadCSV={() => onDownloadCSV?.()}
          />
        </div>
      </div>
    </div>
  );
}
