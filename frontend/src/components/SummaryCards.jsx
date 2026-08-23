/**
 * SummaryCards — four top-line metric cards driven by /api/dashboard/summary.
 */

function fmt(amount) {
  if (amount == null) return '—';
  const n = parseFloat(amount);
  if (n >= 100000) return `₹${(n / 100000).toFixed(1)}L`;
  if (n >= 1000)   return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n.toFixed(0)}`;
}

export default function SummaryCards({ summary, loading, error }) {
  if (loading) {
    return (
      <div className="summary-section">
        <p className="summary-section-title">Overview</p>
        <div className="loading-row"><div className="spinner" /> Loading summary…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="summary-section">
        <p className="summary-section-title">Overview</p>
        <div className="error-banner">Failed to load summary: {error}</div>
      </div>
    );
  }

  const s = summary || {};

  return (
    <div className="summary-section">
      <p className="summary-section-title">Overview</p>
      <div className="summary-cards">

        <div className="summary-card accent">
          <div className="summary-card-label">Revenue at Risk</div>
          <div className="summary-card-value">{fmt(s.total_revenue_at_risk)}</div>
          <div className="summary-card-sub">OPEN + IN PROGRESS cases</div>
        </div>

        <div className="summary-card warn">
          <div className="summary-card-label">Open Cases</div>
          <div className="summary-card-value">{s.open_cases ?? '—'}</div>
          <div className="summary-card-sub">of {s.total_cases ?? '—'} total</div>
        </div>

        <div className="summary-card">
          <div className="summary-card-label">In Progress</div>
          <div className="summary-card-value">{s.in_progress_cases ?? '—'}</div>
          <div className="summary-card-sub">Agent running / pending</div>
        </div>

        <div className="summary-card success">
          <div className="summary-card-label">Recovered Revenue</div>
          <div className="summary-card-value">₹0</div>
          <div className="summary-card-sub">Simulated — no real payments</div>
        </div>

      </div>
    </div>
  );
}
