import { type TestSuiteResult, type TestResultItem } from '../services/api';
import './TestResultsPanel.css';

interface TestResultsPanelProps {
  testResults: TestSuiteResult | null;
  isRunning: boolean;
}

function TestIcon({ status }: { status: TestResultItem['status'] }) {
  switch (status) {
    case 'passed':
      return <span className="test-icon passed">✓</span>;
    case 'failed':
      return <span className="test-icon failed">✗</span>;
    case 'skipped':
      return <span className="test-icon skipped">⊘</span>;
    case 'error':
      return <span className="test-icon error">⚠</span>;
    default:
      return null;
  }
}

function TestResultCard({ test }: { test: TestResultItem }) {
  const hasViolations = test.details?.violations && test.details.violations.length > 0;
  
  return (
    <div className={`test-card ${test.status}`}>
      <div className="test-card-header">
        <TestIcon status={test.status} />
        <span className="test-name">{test.name}</span>
        <span className={`test-status-badge ${test.status}`}>{test.status}</span>
      </div>
      <div className="test-message">{test.message}</div>
      
      {hasViolations && (
        <div className="test-violations">
          <div className="violations-header">Violations:</div>
          <ul className="violations-list">
            {test.details!.violations!.map((v, i) => (
              <li key={i} className="violation-item">{v}</li>
            ))}
          </ul>
        </div>
      )}
      
      {test.details?.summary && (
        <div className="test-summary">
          <div className="summary-header">Parts found:</div>
          <div className="summary-items">
            {Object.entries(test.details.summary).map(([type, count]) => (
              <span key={type} className="summary-item">
                {count}× {type.replace('_', ' ')}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function TestResultsPanel({ 
  testResults, 
  isRunning, 
}: TestResultsPanelProps) {
  return (
    <div className="test-results-panel">
      <div className="test-panel-header">
        <h4>Test Suite</h4>
        {isRunning && <span className="test-running-indicator">Running...</span>}
      </div>
      
      {testResults ? (
        <div className="test-results-content">
          <div className="test-summary-bar">
            <span className={`summary-stat ${testResults.passed > 0 ? 'has-passed' : ''}`}>
              ✓ {testResults.passed} passed
            </span>
            <span className={`summary-stat ${testResults.failed > 0 ? 'has-failed' : ''}`}>
              ✗ {testResults.failed} failed
            </span>
            {testResults.skipped > 0 && (
              <span className="summary-stat has-skipped">
                ⊘ {testResults.skipped} skipped
              </span>
            )}
            {testResults.errors > 0 && (
              <span className="summary-stat has-errors">
                ⚠ {testResults.errors} errors
              </span>
            )}
          </div>
          
          <div className="test-cards">
            {testResults.tests.map((test, i) => (
              <TestResultCard key={i} test={test} />
            ))}
          </div>
        </div>
      ) : (
        <div className="test-empty-state">
          <p>{isRunning ? 'Running tests...' : 'Tests will run automatically after code execution.'}</p>
        </div>
      )}
    </div>
  );
}
