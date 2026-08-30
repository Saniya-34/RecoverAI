/**
 * SummaryCards — top-line merchant metrics from /api/dashboard/summary.
 */

function fmt(amount) {
  if (amount == null) return '—';
  const n = parseFloat(amount);
  if (n >= 100000) return `₹${(n / 100000).toFixed(1)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n.toFixed(0)}`;
}

export default function SummaryCards({ summary, loading, error }) {
  if (loading) {
    return (
      <div className="summary-section">
        <div className="loading-row" style={{ padding: 8 }}>
          <div className="spinner" /> Loading overview…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="summary-section">
        <div className="error-banner" style={{ margin: 0 }}>
          Could not load overview: {error}
        </div>
      </div>
    );
  }

  const s = summary || {};

  return (
    <div className="summary-section">
      <div className="summary-cards">
        <div className="summary-card accent">
          <div className="summary-card-label">Revenue at risk</div>
          <div className="summary-card-value">{fmt(s.total_revenue_at_risk)}</div>
          <div className="summary-card-sub">Open and in-progress cases</div>
        </div>

        <div className="summary-card warn">
          <div className="summary-card-label">Open cases</div>
          <div className="summary-card-value">{s.open_cases ?? '—'}</div>
          <div className="summary-card-sub">of {s.total_cases ?? '—'} total</div>
        </div>

        <div className="summary-card">
          <div className="summary-card-label">In progress</div>
          <div className="summary-card-value">{s.in_progress_cases ?? '—'}</div>
          <div className="summary-card-sub">Currently being recovered</div>
        </div>

        <div className="summary-card success">
          <div className="summary-card-label">Recovered (demo)</div>
          <div className="summary-card-value">{fmt(s.recovered_revenue)}</div>
          <div className="summary-card-sub">Simulated — no real payments</div>
        </div>
      </div>
    </div>
  );
}
