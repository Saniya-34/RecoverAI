/**
 * CaseList — sidebar list of RecoveryCases with status filter.
 */

import StatusBadge from './StatusBadge.jsx';

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
  });
}

function fmtAmount(v) {
  if (v == null) return '—';
  return `₹${parseFloat(v).toLocaleString('en-IN', { minimumFractionDigits: 0 })}`;
}

const TYPE_LABELS = {
  PAYMENT_FAILURE:      'Payment Failure',
  CHECKOUT_ABANDONMENT: 'Checkout Abandonment',
  SUBSCRIPTION_FAILURE: 'Subscription Failure',
  OTHER:                'Other',
};

export default function CaseList({
  cases,
  loading,
  error,
  selectedId,
  onSelect,
  statusFilter,
  onStatusFilterChange,
}) {
  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <p className="sidebar-title">Recovery Cases</p>
        <div className="filter-row">
          <select
            className="filter-select"
            value={statusFilter}
            onChange={e => onStatusFilterChange(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="OPEN">Open</option>
            <option value="IN_PROGRESS">In Progress</option>
            <option value="RECOVERED">Recovered</option>
            <option value="STOPPED">Stopped</option>
            <option value="NOT_RECOVERED">Not Recovered</option>
          </select>
        </div>
      </div>

      <div className="sidebar-list">
        {loading && (
          <div className="loading-row">
            <div className="spinner" /> Loading cases…
          </div>
        )}

        {!loading && error && (
          <div className="error-banner">{error}</div>
        )}

        {!loading && !error && cases.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">📂</div>
            <div className="empty-state-title">No cases found</div>
            <div className="empty-state-desc">
              {statusFilter ? `No ${statusFilter} cases.` : 'No recovery cases yet.'}
            </div>
          </div>
        )}

        {cases.map(c => (
          <div
            key={c.id}
            className={`case-row${selectedId === c.id ? ' selected' : ''}`}
            onClick={() => onSelect(c.id)}
            role="button"
            tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && onSelect(c.id)}
          >
            <div className="case-row-top">
              <span className="case-id">#{c.id}</span>
              <span className="case-amount">{fmtAmount(c.risk_amount)}</span>
            </div>
            <div className="case-row-mid">
              {c.customer?.name || c.customer?.external_customer_id || 'Unknown Customer'}
            </div>
            <div className="case-row-bottom">
              <span className="case-type-label">
                {TYPE_LABELS[c.case_type] ?? c.case_type}
              </span>
              <StatusBadge value={c.status} />
            </div>
            <div className="case-detected">
              Detected {fmtDate(c.detected_at)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
