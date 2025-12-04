import './ActionsPanel.css';

interface ActionsPanelProps {
  onDownloadProject: () => void;
  onDownloadCSV?: () => void;
}

/**
 * Actions panel with download buttons.
 */
export function ActionsPanel({
  onDownloadProject,
  onDownloadCSV,
}: ActionsPanelProps) {
  return (
    <div className="actions-panel">
      <div className="actions-panel-header">
        <h4>Actions</h4>
      </div>
      <div className="actions-panel-content">
        <button
          onClick={onDownloadProject}
          className="action-btn download-project-btn"
        >
          <span className="action-icon">💾</span>
          <span className="action-text">Download Project</span>
        </button>
        {onDownloadCSV && (
          <button
            onClick={onDownloadCSV}
            className="action-btn download-csv-btn"
          >
            <span className="action-icon">📊</span>
            <span className="action-text">Download CSV</span>
          </button>
        )}
      </div>
    </div>
  );
}
