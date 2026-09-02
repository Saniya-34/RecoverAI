/**
 * CaseDetail — matches reference image layout.
 * Left col: AI Recommendation + Payment History
 * Right col: Next Action (Start Recovery) + Audit Timeline
 */

import { useState } from 'react';
import StatusBadge from './StatusBadge.jsx';
import AgentPanel from './AgentPanel.jsx';
import AuditTrail from './AuditTrail.jsx';

const TYPE_LABELS_DISPLAY = {
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
function getName(c) {
  if (!c) return 'Unknown Customer';
  return c.name || c.external_customer_id || 'Unknown Customer';
}
function initials(name) {
  const p = name.trim().split(/\s+/);
  return p.length >= 2 ? (p[0][0] + p[1][0]).toUpperCase() : name.slice(0, 2).toUpperCase();
}
function fmtAmt(v) {
  if (v == null) return '—';
  return `₹${parseFloat(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function fmtCompact(v) {
  if (v == null) return '—';
  const n = parseFloat(v);
  if (n >= 100000) return `₹${(n / 100000).toFixed(1)}L`;
  if (n >= 1000)   return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n.toFixed(0)}`;
}
function fmtDateLong(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}
function fmtPct(v) {
  if (v == null) return '—';
  return `${(parseFloat(v) * 100).toFixed(1)}%`;
}

function DetailSkeleton() {
  return (
    <div className="p-5 flex flex-col gap-4">
      <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
        <div className="flex gap-3 items-center mb-4">
          <div className="skeleton w-10 h-10 rounded-full" />
          <div className="flex-1">
            <div className="skeleton h-5 w-2/5 rounded mb-2"/>
            <div className="skeleton h-3 w-1/3 rounded"/>
          </div>
        </div>
        <div className="grid grid-cols-4 gap-4">
          {[1,2,3,4].map(i => (
            <div key={i}>
              <div className="skeleton h-3 w-3/4 rounded mb-2"/>
              <div className="skeleton h-5 w-1/2 rounded"/>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function CaseDetail({
  caseData, loading, error,
  customerHistory, historyLoading, historyError,
  caseStatus, agentResult, agentRunning, agentError,
  onRunAgent, audit, auditLoading, auditError,
}) {
  const [showMorePayments, setShowMorePayments] = useState(false);

  if (loading && !caseData) return <DetailSkeleton />;
  if (error && !caseData) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-600">
          Couldn&apos;t load this case.
        </div>
      </div>
    );
  }
  if (!caseData) return null;

  const { customer, payment } = caseData;
  const name          = getName(customer);
  const colorCls      = avatarColor(name);
  const historyReady  = Boolean(customerHistory) && !historyLoading;
  const payments      = customerHistory?.payments ?? [];
  const visiblePmts   = showMorePayments ? payments : payments.slice(0, 5);
  const failureReason = payment?.failure_reason || null;
  const isEligible    = (caseStatus === 'OPEN' || caseStatus === 'IN_PROGRESS');

  return (
    <div className="p-5 flex flex-col gap-4 min-h-full">

      {/* ── Customer header ──────────────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {/* Name row */}
        <div className="px-5 py-4 flex items-center justify-between gap-4 border-b border-gray-200">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`w-11 h-11 rounded-full flex items-center justify-center text-[14px] font-extrabold flex-shrink-0 ${colorCls}`}>
              {initials(name)}
            </div>
            <div className="min-w-0">
              <div className="text-[19px] font-extrabold text-gray-900 leading-tight">{name}</div>
              <div className="text-[12px] font-medium text-gray-500 mt-0.5 flex items-center gap-2 flex-wrap">
                {customer?.email && <span>{customer.email}</span>}
                {customer?.external_customer_id && (
                  <>
                    <span className="text-gray-300">·</span>
                    <span>Customer ID: {customer.external_customer_id}</span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <StatusBadge value={caseData.status} />
            <button className="text-gray-400 hover:text-gray-600 p-1 rounded" aria-label="More options">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Facts strip — 4 columns */}
        <div className="grid grid-cols-4 divide-x divide-gray-200">
          <div className="px-5 py-3.5">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 mb-1.5 uppercase tracking-wide">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="1" x2="12" y2="23"/>
                <path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>
              </svg>
              At Risk
            </div>
            <div className="text-[18px] font-black text-orange-600 tracking-tight">{fmtCompact(caseData.risk_amount)}</div>
          </div>

          <div className="px-5 py-3.5">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 mb-1.5 uppercase tracking-wide">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="15" y1="9" x2="9" y2="15"/>
                <line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
              Failure Reason
            </div>
            <div className={`text-[13px] font-bold font-mono ${failureReason ? 'text-red-600' : 'text-gray-400 italic font-sans font-normal'}`}>
              {failureReason ?? 'Not recorded'}
            </div>
          </div>

          <div className="px-5 py-3.5">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 mb-1.5 uppercase tracking-wide">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="2" y="7" width="20" height="14" rx="2"/>
                <path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/>
              </svg>
              Type
            </div>
            <div className="text-[14px] font-bold text-gray-800">
              {TYPE_LABELS_DISPLAY[caseData.case_type] ?? caseData.case_type}
            </div>
          </div>

          <div className="px-5 py-3.5">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 mb-1.5 uppercase tracking-wide">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              Pay Success Rate
            </div>
            <div className="text-[14px] font-bold text-gray-800">
              {historyLoading
                ? <span className="text-gray-400 text-xs font-normal">…</span>
                : historyReady ? fmtPct(customerHistory.success_rate)
                : <span className="text-gray-400">—</span>}
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-2.5 text-sm text-red-600">
          Showing cached data — refresh failed.
        </div>
      )}

      {/* ── Two-column body ───────────────────────────────── */}
      <div className="grid grid-cols-[1fr_300px] gap-4 items-start">

        {/* ══ LEFT COLUMN ══ */}
        <div className="flex flex-col gap-4">

          {/* AI Recommendation */}
          <AgentPanel
            caseStatus={caseStatus ?? caseData.status}
            agentResult={agentResult}
            running={agentRunning}
            error={agentError}
            onRun={onRunAgent}
            riskAmount={caseData.risk_amount}
          />

          {/* Payment History */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-5 py-3.5 border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-2 text-[12px] font-extrabold text-gray-600 uppercase tracking-widest">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="1" y="4" width="22" height="16" rx="2"/>
                  <line x1="1" y1="10" x2="23" y2="10"/>
                </svg>
                Payment History
              </div>
              {historyReady && payments.length > 5 && (
                <button
                  className="text-[13px] font-semibold text-indigo-600 hover:underline"
                  onClick={() => setShowMorePayments(v => !v)}
                >
                  {showMorePayments ? 'Show less' : 'View all history'}
                </button>
              )}
            </div>

            <div className="px-5 py-4">
              {/* Stats row */}
              {historyReady && (
                <div className="flex items-center gap-8 mb-4 pb-4 border-b border-gray-200">
                  <div>
                    <div className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-0.5">Total Payments</div>
                    <div className="text-[22px] font-black text-gray-800">{customerHistory.total_payment_attempts ?? '—'}</div>
                  </div>
                  <div>
                    <div className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-0.5">Success Rate</div>
                    <div className="text-[22px] font-black text-green-600">{fmtPct(customerHistory.success_rate)}</div>
                  </div>
                  <div>
                    <div className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-0.5">Failed Payments</div>
                    <div className="text-[22px] font-black text-red-500">{customerHistory.failed_payments ?? '—'}</div>
                  </div>
                </div>
              )}

              {historyLoading && (
                <div className="flex items-center gap-2 py-4 text-sm text-gray-500">
                  <div className="spinner w-4 h-4" /> Loading…
                </div>
              )}
              {historyError && !historyLoading && (
                <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                  Couldn&apos;t load payment history.
                </div>
              )}
              {historyReady && !historyLoading && payments.length === 0 && (
                <p className="text-[13px] font-medium text-gray-500 py-2">No previous payments for this customer.</p>
              )}
              {historyReady && !historyLoading && payments.length > 0 && (
                <div className="flex flex-col">
                  {visiblePmts.map((p, idx) => {
                    const ok = p.status?.toUpperCase() === 'SUCCESS';
                    return (
                      <div key={p.id || idx}
                        className="flex items-center gap-3 py-2.5 border-b border-gray-100 last:border-0">
                        <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-bold flex-shrink-0
                          ${ok ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
                          {ok ? '✓' : '✕'}
                        </span>
                        <span className="text-[12px] font-medium text-gray-600 w-44 flex-shrink-0">{fmtDateLong(p.attempted_at || p.created_at)}</span>
                        <span className="text-[14px] font-bold text-gray-800 flex-1">{fmtAmt(p.amount)}</span>
                        {p.failure_reason && (
                          <span className="text-[11px] text-gray-500 font-mono truncate max-w-[100px]" title={p.failure_reason}>
                            {p.failure_reason}
                          </span>
                        )}
                        <StatusBadge value={p.status} />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ══ RIGHT COLUMN ══ */}
        <div className="flex flex-col gap-4">

          {/* NEXT ACTION card */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-5 py-3.5 border-b border-gray-200 flex items-center gap-2">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              <span className="text-[12px] font-extrabold text-gray-600 uppercase tracking-widest">Next Action</span>
            </div>

            <div className="px-5 py-5 flex flex-col items-center text-center gap-3">
              {agentRunning ? (
                <div className="flex items-center gap-2 text-[14px] text-indigo-600 font-semibold py-4">
                  <div className="spinner w-4 h-4" /> Analyzing…
                </div>
              ) : (
                <>
                  <p className="text-[13px] font-semibold text-gray-600">Start recovery for this case</p>
                  <div className="text-[30px] font-black text-orange-600 tracking-tight leading-none">
                    {fmtCompact(caseData.risk_amount)}
                  </div>

                  {isEligible ? (
                    <button
                      onClick={onRunAgent}
                      disabled={agentRunning}
                      className="w-full flex items-center justify-center gap-2 py-3 px-5 bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold text-[14px] rounded-xl shadow-sm transition-all hover:shadow-md active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                        <polygon points="5 3 19 12 5 21 5 3"/>
                      </svg>
                      Start Recovery
                    </button>
                  ) : (
                    <div className="w-full py-3 px-5 bg-gray-100 text-gray-500 font-bold text-[13px] rounded-xl text-center">
                      Recovery unavailable
                    </div>
                  )}

                  <div className="flex items-center gap-1.5 text-[12px] font-medium text-gray-500">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
                      <polyline points="22 4 12 14.01 9 11.01"/>
                    </svg>
                    No real payments will be processed.
                  </div>
                </>
              )}

              {agentError && (
                <div className="w-full text-[13px] font-medium text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                  Recovery failed. Try again.
                </div>
              )}
            </div>
          </div>

          {/* Audit Timeline */}
          <AuditTrail audit={audit} loading={auditLoading} error={auditError} />
        </div>
      </div>
    </div>
  );
}
