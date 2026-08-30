/**
 * CaseList — compact, searchable sidebar of recovery cases.
 */

import { useMemo, useState } from 'react';
import StatusBadge from './StatusBadge.jsx';
const TYPE_LABELS = {
  PAYMENT_FAILURE: 'Failed payment',
  CHECKOUT_ABANDONMENT: 'Abandoned checkout',
  SUBSCRIPTION_FAILURE: 'Failed subscription',
  OTHER: 'Other',
};

function customerName(customer) {
  if (!customer) return 'Unknown Customer';
  return customer.name || customer.external_customer_id || 'Unknown Customer';
}

function fmtAmountCompact(v) {
  if (v == null) return '—';
  const n = parseFloat(v);
  if (n >= 100000) return `₹${(n / 100000).toFixed(1)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n.toFixed(0)}`;
}

function fmtDateShort(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
  });
}


export default function CaseList({
  cases,
  loading,
  error,
  selectedId,
  onSelect,
  statusFilter,
  onStatusFilterChange,
  typeFilter,
  onTypeFilterChange,
}) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('newest');

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = cases;
    if (q) {
      rows = rows.filter((c) => {
        const name = customerName(c.customer).toLowerCase();
        const email = (c.customer?.email || '').toLowerCase();
        const type = (TYPE_LABELS[c.case_type] || c.case_type || '').toLowerCase();
        return (
          name.includes(q) ||
          email.includes(q) ||
          type.includes(q) ||
          String(c.id).includes(q)
        );
      });
    }
    const copy = [...rows];
    copy.sort((a, b) => {
      if (sort === 'oldest') {
        return new Date(a.detected_at) - new Date(b.detected_at);
      }
      if (sort === 'amount-desc') {
        return parseFloat(b.risk_amount) - parseFloat(a.risk_amount);
      }
      if (sort === 'amount-asc') {
        return parseFloat(a.risk_amount) - parseFloat(b.risk_amount);
      }
      return new Date(b.detected_at) - new Date(a.detected_at);
    });
    return copy;
  }, [cases, query, sort]);

  return (
    <aside className="sidebar" aria-label="Recovery cases">
      <div className="sidebar-header">
        <div className="sidebar-title-row">
          <p className="sidebar-title">Customers at risk</p>
          <span className="sidebar-count">{visible.length}</span>
        </div>

        <input
          className="filter-search"
          type="search"
          placeholder="Search name, email, or case…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search cases"
        />

        <div className="filter-row">
          <select
            className="filter-select"
            value={statusFilter}
            onChange={(e) => onStatusFilterChange(e.target.value)}
            aria-label="Filter by status"
          >
            <option value="">All statuses</option>
            <option value="OPEN">Open</option>
            <option value="IN_PROGRESS">In progress</option>
            <option value="RECOVERED">Recovered</option>
            <option value="STOPPED">Stopped</option>
            <option value="NOT_RECOVERED">Not recovered</option>
          </select>
          <select
            className="filter-select"
            value={typeFilter}
            onChange={(e) => onTypeFilterChange(e.target.value)}
            aria-label="Filter by case type"
          >
            <option value="">All types</option>
            <option value="PAYMENT_FAILURE">Failed payment</option>
            <option value="CHECKOUT_ABANDONMENT">Abandoned checkout</option>
            <option value="SUBSCRIPTION_FAILURE">Failed subscription</option>
            <option value="OTHER">Other</option>
          </select>
        </div>
        <select
          className="filter-select"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          aria-label="Sort cases"
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="amount-desc">Highest amount</option>
          <option value="amount-asc">Lowest amount</option>
        </select>
      </div>

      <div className="sidebar-list" role="list">
        {loading && cases.length === 0 && (
          <div className="loading-row">
            <div className="spinner" /> Loading cases…
          </div>
        )}

        {!loading && error && (
          <div className="error-banner">{error}</div>
        )}

        {!loading && !error && cases.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-title">No cases yet</div>
            <div className="empty-state-desc">
              {statusFilter || typeFilter
                ? 'Nothing matches these filters.'
                : 'When a payment fails or checkout is abandoned, it will show up here.'}
            </div>
          </div>
        )}

        {!error && cases.length > 0 && visible.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-title">No matching customers</div>
            <div className="empty-state-desc">Try a different search or filter.</div>
          </div>
        )}

        {visible.map((c) => (
          <div
            key={c.id}
            className={`case-row${selectedId === c.id ? ' selected' : ''}`}
            onClick={() => onSelect(c.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect(c.id);
              }
            }}
          >
            <div className="case-row-top">
              <span className="case-row-name">{customerName(c.customer)}</span>
              <span className="case-amount">{fmtAmountCompact(c.risk_amount)}</span>
            </div>
            <div className="case-row-bottom">
              <span className="case-type-label">
                {TYPE_LABELS[c.case_type] ?? c.case_type}
              </span>
              <StatusBadge value={c.status} />
            </div>
            <div className="case-detected">{fmtDateShort(c.detected_at)}</div>
          </div>
        ))}
      </div>
    </aside>
  );
}
