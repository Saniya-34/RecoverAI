/**
 * AgentPanel — Run Recovery Agent button + result display.
 *
 * IMPORTANT: clearly shows SIMULATED on every result.
 * Never implies real money was moved.
 */

import StatusBadge from './StatusBadge.jsx';

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric', month: 'short',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
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
      {/* ── Run button ── */}
      <div className="agent-section">
        {running ? (
          <div className="agent-running-label">
            <div className="spinner" />
            Analyzing recovery opportunity…
          </div>
        ) : (
          <button
            className="btn-run-agent"
            onClick={onRun}
            disabled={!isEligible || running}
            title={!isEligible ? `Case is ${caseStatus} — not eligible for agent run` : ''}
          >
            ▶ Run Recovery Agent
          </button>
        )}

        {!isEligible && !running && (
          <span className="agent-hint">
            Only OPEN or IN_PROGRESS cases can be processed.
          </span>
        )}

        {error && (
          <div className="error-banner" style={{ margin: 0 }}>
            Recovery agent failed: {error}
          </div>
        )}
      </div>

      {/* ── Result card ── */}
      {r && (
        <div className="agent-result-section">
          <p className="detail-section-title">Agent Result</p>
          <div className="agent-result-card">

            {/* Decision + Action */}
            <div className="agent-result-header">
              <span className="agent-result-title">Decision</span>
              <StatusBadge value={r.decision} />
              <span className="agent-result-title" style={{ marginLeft: 12 }}>Action</span>
              <StatusBadge value={r.action} />
              {r.policy_override && (
                <span className="chip chip-stop" style={{ marginLeft: 8 }}>
                  Policy Override
                </span>
              )}
            </div>

            {/* Confidence */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 12, color: 'var(--text)' }}>Confidence</span>
              <ConfidenceBar value={r.confidence} />
            </div>

            {/* Reason */}
            <div>
              <div style={{ fontSize: 11, color: 'var(--text)', fontWeight: 600,
                textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 4 }}>
                Reason
              </div>
              <div className="agent-reason">{r.reason}</div>
            </div>

            {/* Evidence */}
            {r.evidence && r.evidence.length > 0 && (
              <div>
                <div style={{ fontSize: 11, color: 'var(--text)', fontWeight: 600,
                  textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 6 }}>
                  Evidence
                </div>
                <div className="evidence-list">
                  {r.evidence.map((e, i) => (
                    <div key={i} className="evidence-item">
                      <span className="evidence-dot">◆</span>
                      {e}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Simulated action result */}
            {r.action_result && (
              <div>
                <div className="simulated-notice">
                  ⚠ SIMULATED ACTION — No real payments were made. No money moved.
                </div>
                <div className="action-result-row" style={{ marginTop: 10 }}>
                  <span style={{ fontSize: 12, color: 'var(--text)' }}>Action Status:</span>
                  <span className="chip chip-simulated">SIMULATED</span>
                  <span style={{ fontSize: 12, color: 'var(--text)' }}>
                    {r.action_result.success ? '✓ Success (simulated)' : '✗ Failed'}
                  </span>
                </div>
                {r.action_result.message && (
                  <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text)',
                    fontStyle: 'italic', lineHeight: 1.5 }}>
                    {r.action_result.message}
                  </div>
                )}
                <div className="action-result-row" style={{ marginTop: 8 }}>
                  <span style={{ fontSize: 12, color: 'var(--text)' }}>Money Recovered:</span>
                  <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-h)' }}>₹0</span>
                  <span style={{ fontSize: 11, color: 'var(--text)' }}>
                    (simulation — not real)
                  </span>
                </div>
              </div>
            )}

            {/* Completed at */}
            {r.completed_at && (
              <div style={{ fontSize: 11, color: 'var(--text)', borderTop: '1px solid var(--border)',
                paddingTop: 10, marginTop: 2 }}>
                Completed at {fmtDate(r.completed_at)}
                {r.agent_action_id && (
                  <span style={{ marginLeft: 12 }}>
                    Agent Action #{r.agent_action_id}
                  </span>
                )}
              </div>
            )}

          </div>
        </div>
      )}
    </>
  );
}
