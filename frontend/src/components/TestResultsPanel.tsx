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
  const hasParts = test.details?.parts && test.details.parts.length > 0;
  const hasIntersections = test.details?.intersection_descriptions && test.details.intersection_descriptions.length > 0;
  
  const formatPartType = (type: string) => {
    return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };
  
  const formatDimensions = (dims: number[] | Record<string, number>) => {
    // Handle both array format [smallest, middle, largest] and legacy dict format
    if (Array.isArray(dims)) {
      return `${dims[0]}×${dims[1]}×${dims[2]}mm`;
    }
    return `${dims.x}×${dims.y}×${dims.z}mm`;
  };
  
  const getPartDescription = (classification: Record<string, unknown>) => {
    const type = classification.type as string;
    if (type === 'beam_28x28' || type === 'beam_48x24') {
      return `${formatPartType(type)} - Length: ${classification.length}mm`;
    } else if (type === 'plywood') {
      return `Plywood - ${classification.width}×${classification.height}mm (${classification.thickness}mm thick)`;
    }
    return formatPartType(type);
  };
  
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
      
      {hasIntersections && (
        <div className="test-intersections">
          <div className="intersections-header">Intersections:</div>
          <ul className="intersections-list">
            {test.details!.intersection_descriptions!.map((desc: string, i: number) => (
              <li key={i} className="intersection-item">{desc}</li>
            ))}
          </ul>
        </div>
      )}
      
      {hasParts && (
        <div className="test-parts-list">
          <div className="parts-header">Parts Found ({test.details!.parts!.length}):</div>
          <div className="parts-table">
            {test.details!.parts!.map((part) => (
              <div key={part.index} className="part-row">
                <span className="part-index">#{part.index}</span>
                <span className="part-type">{getPartDescription(part.classification)}</span>
                <span className="part-dims">{formatDimensions(part.dimensions)}</span>
              </div>
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
        <h4>Assembly Test Suite</h4>
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
