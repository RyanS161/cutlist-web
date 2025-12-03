import './ActionsPanel.css';

interface ActionsPanelProps {
  onReviewImage: () => void;
  onReviewTestResults: () => void;
  onQAReview: () => void;
  onDownloadProject: () => void;
  canReviewImage: boolean;
  canReviewTests: boolean;
  canQAReview: boolean;
  isReviewing: boolean;
  isQAReviewing: boolean;
}

/**
 * Actions panel with buttons to trigger AI reviews.
 */
export function ActionsPanel({
  onReviewImage,
  onReviewTestResults,
  onQAReview,
  onDownloadProject,
  canReviewImage,
  canReviewTests,
  canQAReview,
  isReviewing,
  isQAReviewing,
}: ActionsPanelProps) {
  const isAnyReviewing = isReviewing || isQAReviewing;
  
  return (
    <div className="actions-panel">
      <div className="actions-panel-header">
        <h4>Actions</h4>
      </div>
      <div className="actions-panel-content">
        <button
          onClick={onQAReview}
          disabled={!canQAReview || isAnyReviewing}
          className="action-btn qa-review-btn"
        >
          <span className="action-icon">🤖</span>
          <span className="action-text">Trigger QA Agent Review</span>
        </button>
        <button
          onClick={onReviewImage}
          disabled={!canReviewImage || isAnyReviewing}
          className="action-btn review-image-btn"
        >
          <span className="action-icon">🔍</span>
          <span className="action-text">Send Image to Agent for Review</span>
        </button>
        <button
          onClick={onReviewTestResults}
          disabled={!canReviewTests || isAnyReviewing}
          className="action-btn review-tests-btn"
        >
          <span className="action-icon">📋</span>
          <span className="action-text">Send Test Results to Agent for Review</span>
        </button>
        <button
          onClick={onDownloadProject}
          disabled={isAnyReviewing}
          className="action-btn download-project-btn"
        >
          <span className="action-icon">💾</span>
          <span className="action-text">Download Project</span>
        </button>
        {isAnyReviewing && (
          <div className="reviewing-indicator">
            <span className="reviewing-spinner">⟳</span>
            <span>{isQAReviewing ? 'QA Agent reviewing...' : 'Reviewing...'}</span>
          </div>
        )}
      </div>
    </div>
  );
}
