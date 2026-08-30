/**
 * AuditTrail — collapsible activity log. Technical payloads stay hidden by default.
 */

const AUDIT_EVENT_LABELS = {
  // Add more event types as needed
  case_created: "Case Created",
  decision_made: "Decision Made",
  action_taken: "Action Taken",
};

function fmtDate(dateStr) {
  const d = new Date(dateStr);
  return isNaN(d) ? "—" : d.toLocaleString();
}

function labelFor(key, map) {
  return map[key] ?? String(key).replace(/_/g, " ");
}


export default function AuditTrail({ audit, loading, error }) {
  return (
    <section className="detail-section audit-section">
      <details className="audit-disclosure">
        <summary className="detail-section-title">Audit history</summary>

        {loading && (
          <div className="loading-row">
            <div className="spinner" /> Loading activity…
          </div>
        )}

        {!loading && error && (
          <div className="error-banner">Could not load activity: {error}</div>
        )}

        {!loading && !error && (!audit || audit.entries?.length === 0) && (
          <div className="empty-state" style={{ padding: '24px' }}>
            <div className="empty-state-title">No activity yet</div>
            <div className="empty-state-desc">
              Start recovery to record what happened on this case.
            </div>
          </div>
        )}

        {audit?.entries && audit.entries.length > 0 && (
          <div className="audit-timeline">
            {audit.entries.map((entry, idx) => {
              const isLast = idx === audit.entries.length - 1;
              return (
                <div key={entry.id} className="audit-entry">
                  <div className="audit-line-col">
                    <div className="audit-dot" />
                    {!isLast && <div className="audit-connector" />}
                  </div>
                  <div className="audit-content">
                    <div className="audit-event-type">
                      {labelFor(entry.event_type, AUDIT_EVENT_LABELS)}
                    </div>
                    <div className="audit-meta">
                      {entry.actor} · {fmtDate(entry.created_at)}
                    </div>
                    {entry.details && Object.keys(entry.details).length > 0 && (
                      <details className="tech-details">
                        <summary>Technical details</summary>
                        <div className="audit-details">
                          {Object.entries(entry.details).map(([k, v]) => (
                            <div key={k}>
                              <span style={{ color: 'var(--accent)' }}>{k}</span>
                              {': '}
                              {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </details>
    </section>
  );
}
