/**
 * CaseList — matches reference image.
 * Larger font sizes, avatar circles, name/type/amount/status/date, pagination.
 */

import { useMemo, useState } from 'react';
import StatusBadge from './StatusBadge.jsx';

const TYPE_LABELS = {
  PAYMENT_FAILURE:      'Failed payment',
  CHECKOUT_ABANDONMENT: 'Abandoned checkout',
  SUBSCRIPTION_FAILURE: 'Failed subscription',
  OTHER:                'Other',
};

const AVATAR_COLORS = [
  'bg-violet-100 text-violet-700',
  'bg-blue-100 text-blue-700',
  'bg-green-100 text-green-700',
  'bg-orange-100 text-orange-700',
  'bg-pink-100 text-pink-700',
  'bg-teal-100 text-teal-700',
  'bg-amber-100 text-amber-700',
  'bg-indigo-100 text-indigo-700',
];
function avatarColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}
function initials(name) {
  const p = name.trim().split(/\s+/);
  return p.length >= 2 ? (p[0][0] + p[1][0]).toUpperCase() : name.slice(0, 2).toUpperCase();
}
function customerName(c) {
  if (!c) return 'Unknown';
  return c.name || c.external_customer_id || 'Unknown';
}
function fmtCompact(v) {
  if (v == null) return '—';
  const n = parseFloat(v);
  if (n >= 100000) return `₹${(n / 100000).toFixed(1)}L`;
  if (n >= 1000)   return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n.toFixed(0)}`;
}
function fmtDateShort(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

const PAGE_SIZE = 6;

function SkeletonRow() {
  return (
    <div className="px-4 py-4 border-b border-gray-200 flex items-center gap-3">
      <div className="skeleton w-11 h-11 rounded-full flex-shrink-0" />
      <div className="flex-1 flex flex-col gap-2">
        <div className="skeleton h-4 w-2/5 rounded" />
        <div className="skeleton h-3 w-1/3 rounded" />
      </div>
      <div className="skeleton h-4 w-12 rounded" />
    </div>
  );
}

export default function CaseList({
  cases, loading, error, selectedId, onSelect,
  statusFilter, onStatusFilterChange, typeFilter, onTypeFilterChange,
}) {
  const [query, setQuery]   = useState('');
  const [sort, setSort]     = useState('newest');
  const [page, setPage]     = useState(1);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = cases;
    if (q) {
      rows = rows.filter(c => {
        const name  = customerName(c.customer).toLowerCase();
        const email = (c.customer?.email || '').toLowerCase();
        const type  = (TYPE_LABELS[c.case_type] || c.case_type || '').toLowerCase();
        return name.includes(q) || email.includes(q) || type.includes(q) || String(c.id).includes(q);
      });
    }
    const copy = [...rows];
    copy.sort((a, b) => {
      if (sort === 'oldest')      return new Date(a.detected_at) - new Date(b.detected_at);
      if (sort === 'amount-desc') return parseFloat(b.risk_amount) - parseFloat(a.risk_amount);
      if (sort === 'amount-asc')  return parseFloat(a.risk_amount) - parseFloat(b.risk_amount);
      return new Date(b.detected_at) - new Date(a.detected_at);
    });
    return copy;
  }, [cases, query, sort]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage   = Math.min(page, totalPages);
  const visible    = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  // Reset page on filter/search change
  const handleQuery  = v => { setQuery(v);  setPage(1); };
  const handleStatus = v => { onStatusFilterChange(v); setPage(1); };
  const handleType   = v => { onTypeFilterChange(v);   setPage(1); };
  const handleSort   = v => { setSort(v);   setPage(1); };

  return (
    <aside className="flex flex-col overflow-hidden min-h-0 h-full bg-white" aria-label="Recovery cases">

      {/* ── Header ── */}
      <div className="px-4 pt-4 pb-3 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <span className="text-[14px] font-extrabold text-gray-800 tracking-tight uppercase">
            Customers At Risk
          </span>
          <span className="text-[12px] font-bold text-white bg-violet-600 px-2.5 py-0.5 rounded-full">
            {filtered.length}
          </span>
        </div>

        {/* Search */}
        <div className="relative mb-2.5">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="6.5" cy="6.5" r="4.5"/><line x1="10" y1="10" x2="14" y2="14"/>
          </svg>
          <input
            className="w-full pl-9 pr-3 py-2 text-[13px] font-medium border border-gray-200 rounded-lg bg-gray-50 text-gray-800 outline-none focus:border-violet-400 focus:bg-white focus:ring-2 focus:ring-violet-100 transition placeholder:text-gray-400"
            type="search"
            placeholder="Search customers or cases..."
            value={query}
            onChange={e => handleQuery(e.target.value)}
            aria-label="Search cases"
          />
        </div>

        {/* Filter row — stacked: status+type on top, sort below */}
        <div className="flex flex-col gap-1.5">
          <div className="flex gap-1.5">
            <select
              className="flex-1 min-w-0 text-[12px] font-medium border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700 outline-none cursor-pointer appearance-none focus:border-violet-400"
              value={statusFilter} onChange={e => handleStatus(e.target.value)}>
              <option value="">All Statuses</option>
              <option value="OPEN">Open</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="RECOVERED">Recovered</option>
              <option value="STOPPED">Stopped</option>
              <option value="NOT_RECOVERED">Not Recovered</option>
            </select>
            <select
              className="flex-1 min-w-0 text-[12px] font-medium border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700 outline-none cursor-pointer appearance-none focus:border-violet-400"
              value={typeFilter} onChange={e => handleType(e.target.value)}>
              <option value="">All Types</option>
              <option value="PAYMENT_FAILURE">Failed payment</option>
              <option value="CHECKOUT_ABANDONMENT">Abandoned</option>
              <option value="SUBSCRIPTION_FAILURE">Subscription</option>
              <option value="OTHER">Other</option>
            </select>
          </div>
          <select
            className="w-full text-[12px] font-medium border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700 outline-none cursor-pointer appearance-none focus:border-violet-400"
            value={sort} onChange={e => handleSort(e.target.value)}>
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
            <option value="amount-desc">Highest Amount</option>
            <option value="amount-asc">Lowest Amount</option>
          </select>
        </div>
      </div>

      {/* ── List ── */}
      <div className="flex-1 overflow-y-auto min-h-0 scrollbar-thin" role="list">
        {loading && cases.length === 0 && (
          <><SkeletonRow/><SkeletonRow/><SkeletonRow/><SkeletonRow/><SkeletonRow/><SkeletonRow/></>
        )}
        {!loading && error && (
          <div className="p-4 text-sm text-red-600 bg-red-50 mx-4 mt-3 rounded-lg border border-red-200">
            Couldn&apos;t load cases.
          </div>
        )}
        {!loading && !error && cases.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 px-4 text-center">
            <p className="text-[13px] font-semibold text-gray-500">No cases yet</p>
            <p className="text-[12px] text-gray-400 max-w-[180px]">
              {statusFilter || typeFilter ? 'No cases match these filters.' : 'Cases will appear here.'}
            </p>
          </div>
        )}
        {!error && cases.length > 0 && visible.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 px-4 text-center">
            <p className="text-[13px] font-semibold text-gray-500">No results</p>
            <p className="text-[12px] text-gray-400">Try a different search.</p>
          </div>
        )}

        {visible.map(c => {
          const name     = customerName(c.customer);
          const iniStr   = initials(name);
          const colorCls = avatarColor(name);
          const isSelected = selectedId === c.id;

          return (
            <div
              key={c.id}
              className={`px-4 py-4 border-b border-gray-200 cursor-pointer transition-colors flex items-center gap-3
                ${isSelected
                  ? 'bg-violet-50 border-l-[3px] border-l-violet-600'
                  : 'hover:bg-gray-50 border-l-[3px] border-l-transparent'}`}
              onClick={() => onSelect(c.id)}
              role="button" tabIndex={0}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(c.id); } }}
            >
              {/* Avatar */}
              <div className={`w-11 h-11 rounded-full flex items-center justify-center text-[13px] font-extrabold flex-shrink-0 ${colorCls}`}>
                {iniStr}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[14px] font-bold text-gray-900 truncate">{name}</span>
                  <span className="text-[13px] font-extrabold text-orange-600 flex-shrink-0">{fmtCompact(c.risk_amount)}</span>
                </div>
                <div className="flex items-center justify-between gap-2 mt-1">
                  <span className="text-[12px] font-medium text-gray-500 truncate">{TYPE_LABELS[c.case_type] ?? c.case_type}</span>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <StatusBadge value={c.status} />
                    <span className="text-[11px] font-medium text-gray-500">{fmtDateShort(c.detected_at)}</span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Pagination ── */}
      {filtered.length > PAGE_SIZE && (
        <div className="px-4 py-3 border-t border-gray-100 flex-shrink-0 flex items-center justify-between gap-2">
          <span className="text-[11px] text-gray-400">
            Showing {(safePage - 1) * PAGE_SIZE + 1} to {Math.min(safePage * PAGE_SIZE, filtered.length)} of {filtered.length} cases
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={safePage === 1}
              className="w-6 h-6 rounded flex items-center justify-center text-gray-500 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition"
              aria-label="Previous page"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="10 4 6 8 10 12"/></svg>
            </button>

            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              let pg;
              if (totalPages <= 5) {
                pg = i + 1;
              } else if (safePage <= 3) {
                pg = i + 1;
              } else if (safePage >= totalPages - 2) {
                pg = totalPages - 4 + i;
              } else {
                pg = safePage - 2 + i;
              }
              return (
                <button
                  key={pg}
                  onClick={() => setPage(pg)}
                  className={`w-6 h-6 rounded text-[11px] font-semibold transition ${
                    pg === safePage
                      ? 'bg-violet-600 text-white'
                      : 'text-gray-500 hover:bg-gray-100'
                  }`}
                >
                  {pg}
                </button>
              );
            })}

            {totalPages > 5 && safePage < totalPages - 2 && (
              <>
                <span className="text-[11px] text-gray-400 px-0.5">…</span>
                <button
                  onClick={() => setPage(totalPages)}
                  className="w-6 h-6 rounded text-[11px] font-semibold text-gray-500 hover:bg-gray-100 transition"
                >
                  {totalPages}
                </button>
              </>
            )}

            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={safePage === totalPages}
              className="w-6 h-6 rounded flex items-center justify-center text-gray-500 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition"
              aria-label="Next page"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 4 10 8 6 12"/></svg>
            </button>
          </div>
        </div>
      )}

      {/* Footer when no pagination */}
      {filtered.length > 0 && filtered.length <= PAGE_SIZE && (
        <div className="px-4 py-2.5 text-[11px] text-gray-400 border-t border-gray-100 flex-shrink-0">
          Showing {filtered.length} of {cases.length} cases
        </div>
      )}
    </aside>
  );
}
