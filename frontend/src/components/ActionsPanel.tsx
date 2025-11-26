import './ActionsPanel.css';

interface ActionsPanelProps {
  onReviewImage: () => void;
  onReviewTestResults: () => void;
  canReviewImage: boolean;
  canReviewTests: boolean;
  isReviewing: boolean;
}

/**
 * Actions panel with buttons to trigger AI reviews.
 */
export function ActionsPanel({
  onReviewImage,
  onReviewTestResults,
  canReviewImage,
  canReviewTests,
  isReviewing,
}: ActionsPanelProps) {
  return (
    <div className="actions-panel">
      <div className="actions-panel-header">
        <h4>Actions</h4>
      </div>
      <div className="actions-panel-content">
        <button
          onClick={onReviewImage}
          disabled={!canReviewImage || isReviewing}
          className="action-btn review-image-btn"
        >
          <span className="action-icon">🔍</span>
          <span className="action-text">Send Image to Agent for Review</span>
        </button>
        <button
          onClick={onReviewTestResults}
          disabled={!canReviewTests || isReviewing}
          className="action-btn review-tests-btn"
        >
          <span className="action-icon">📋</span>
          <span className="action-text">Send Test Results to Agent for Review</span>
        </button>
        {isReviewing && (
          <div className="reviewing-indicator">
            <span className="reviewing-spinner">⟳</span>
            <span>Reviewing...</span>
          </div>
        )}
      </div>
    </div>
  );
}
