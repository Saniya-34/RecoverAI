/**
 * AuditTrail — timeline of audit log entries for the selected case.
 */

function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric', month: 'short',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

const EVENT_ICONS = {
  AGENT_STARTED:                '🚀',
  CASE_LOADED:                  '📂',
  CUSTOMER_HISTORY_RETRIEVED:   '👤',
  PAYMENT_HISTORY_RETRIEVED:    '💳',
  RECOVERY_ATTEMPTS_RETRIEVED:  '🔄',
  DECISION_MADE:                '🧠',
  POLICY_CHECKED:               '🛡️',
  ACTION_SELECTED:              '✅',
  ACTION_EXECUTED:              '⚡',
  CASE_UPDATED:                 '📝',
  AGENT_COMPLETED:              '🎯',
  AGENT_ERROR:                  '❌',
};

export default function AuditTrail({ audit, loading, error }) {
  return (
    <div className="audit-section">
      <p className="detail-section-title">Audit History</p>

      {loading && (
        <div className="loading-row"><div className="spinner" /> Loading audit trail…</div>
      )}

      {!loading && error && (
        <div className="error-banner">Failed to load audit: {error}</div>
      )}

      {!loading && !error && (!audit || audit.entries?.length === 0) && (
        <div className="empty-state" style={{ padding: '24px' }}>
          <div className="empty-state-title">No audit events yet</div>
          <div className="empty-state-desc">
            Run the agent to generate audit events.
          </div>
        </div>
      )}

      {audit?.entries && audit.entries.length > 0 && (
        <div className="audit-timeline">
          {audit.entries.map((entry, idx) => {
            const isLast = idx === audit.entries.length - 1;
            const icon = EVENT_ICONS[entry.event_type] ?? '●';
            return (
              <div key={entry.id} className="audit-entry">
                <div className="audit-line-col">
                  <div className="audit-dot" />
                  {!isLast && <div className="audit-connector" />}
                </div>
                <div className="audit-content">
                  <div className="audit-event-type">
                    {icon} {entry.event_type}
                  </div>
                  <div className="audit-meta">
                    {entry.actor} · {fmtDate(entry.created_at)}
                  </div>
                  {entry.details && Object.keys(entry.details).length > 0 && (
                    <div className="audit-details">
                      {Object.entries(entry.details).map(([k, v]) => (
                        <div key={k}>
                          <span style={{ color: 'var(--accent)' }}>{k}</span>
                          {': '}
                          {typeof v === 'object'
                            ? JSON.stringify(v)
                            : String(v)}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
