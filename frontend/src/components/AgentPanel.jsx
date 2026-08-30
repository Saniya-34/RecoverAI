/**
 * AgentPanel — AI decision + recovery action.
 * Simulated actions are clearly labelled — no real money is moved.
 */

import StatusBadge from './StatusBadge.jsx';
import SimulatedBadge from './SimulatedBadge.jsx';

function fmtAmount(v) {
  if (v == null) return '—';
  return `₹${parseFloat(v).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function ConfidenceBar({ value }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div className="confidence-bar-wrap">
      <div className="confidence-bar">
        <div className="confidence-fill" style={{ width: `${pct}%` }} />
      </div>
      <span>{pct}%</span>
    </div>
  );
}

export default function AgentPanel({
  caseStatus,
  agentResult,
  running,
  error,
  onRun,
}) {
  const isEligible = caseStatus === 'OPEN' || caseStatus === 'IN_PROGRESS';
  const r = agentResult;

  return (
    <>
      <section className="detail-section">
        <div className="detail-section-heading">
          <h2 className="detail-section-title">AI recovery decision</h2>
        </div>

        {!r && !running && (
          <p className="muted-copy">
            This case has not been analyzed yet. Start recovery to get a
            recommendation.
          </p>
        )}

        {running && (
          <div className="agent-running-label">
            <div className="spinner" />
            Reviewing this customer and recommending a next step…
          </div>
        )}

        {r && (
          <div className="agent-result-card">
            <div className="agent-result-header">
              <div className="agent-result-pair">
                <span className="detail-label">Decision</span>
                <StatusBadge value={r.decision} />
              </div>
              <div className="agent-result-pair">
                <span className="detail-label">Recommended action</span>
                <StatusBadge value={r.action} />
              </div>
              {r.policy_override && (
                <span className="chip chip-stop">Safety rule applied</span>
              )}
            </div>

            <div className="confidence-row">
              <span className="detail-label">How sure the AI is</span>
              <ConfidenceBar value={r.confidence} />
            </div>

            <div>
              <div className="detail-label" style={{ marginBottom: 4 }}>Why</div>
              <div className="agent-reason">{r.reason}</div>
            </div>

            {r.evidence && r.evidence.length > 0 && (
              <details className="tech-details">
                <summary>Facts used for this decision</summary>
                <div className="evidence-list">
                  {r.evidence.map((e, i) => (
                    <div key={i} className="evidence-item">
                      <span className="evidence-dot">◆</span>
                      {e}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </section>

      <section className="detail-section agent-section">
        <div className="detail-section-heading">
          <h2 className="detail-section-title">Recovery action</h2>
        </div>

        <div className="agent-actions">
          {running ? (
            <div className="agent-running-label">
              <div className="spinner" />
              Working…
            </div>
          ) : (
            <button
              className="btn-run-agent"
              onClick={onRun}
              disabled={!isEligible || running}
              title={!isEligible ? `This case is ${caseStatus} and cannot be processed again` : ''}
            >
              Start recovery
            </button>
          )}
          <span className="agent-hint">
            Demo only — no real payments or charges.
          </span>
        </div>

        {!isEligible && !running && (
          <p className="agent-hint" style={{ marginTop: 8 }}>
            Only open or in-progress cases can be recovered.
          </p>
        )}

        {error && (
          <div className="error-banner" style={{ margin: '12px 0 0' }}>
            Recovery could not be started: {error}
          </div>
        )}

        {r?.action_result && (
          <div className="action-outcome">
            <div className="simulated-notice">
              Demo action — no real payments were made.
            </div>
            <div className="detail-grid" style={{ marginTop: 12 }}>
              <div className="detail-field">
                <span className="detail-label">Case status</span>
                <span className="detail-value" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <StatusBadge value={caseStatus} />
                  <SimulatedBadge />
                </span>
              </div>
              <div className="detail-field">
                <span className="detail-label">Result</span>
                <span
                  className="detail-value"
                  style={{
                    fontWeight: 600,
                    color: r.action_result.success ? '#4ade80' : '#f87171',
                  }}
                >
                  {r.action_result.success ? 'Succeeded' : 'Did not succeed'}
                </span>
              </div>
              <div className="detail-field">
                <span className="detail-label">Payment outcome</span>
                <span className="detail-value">
                  <StatusBadge value={r.action_result.payment_outcome} />
                </span>
              </div>
              <div className="detail-field">
                <span className="detail-label">Amount recovered (demo)</span>
                <span className="detail-value amount">{fmtAmount(r.recovered_amount)}</span>
              </div>
            </div>
            {r.action_result.message && (
              <p className="action-message">{r.action_result.message}</p>
            )}
            {r.completed_at && (
              <p className="muted-copy" style={{ marginTop: 10 }}>
                Finished {fmtDate(r.completed_at)}
              </p>
            )}
          </div>
        )}
      </section>
    </>
  );
}
