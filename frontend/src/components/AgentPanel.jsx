/**
 * AgentPanel — AI Recommendation card matching reference image.
 * Shows RECOVER/decision in large text, confidence badge, recommended action,
 * reason text, and collapsible factors.
 */

import { useState } from 'react';
import StatusBadge from './StatusBadge.jsx';
import SimulatedBadge from './SimulatedBadge.jsx';

const ACTION_NAMES = {
  RETRY_PAYMENT:     'Retry Payment',
  SEND_PAYMENT_LINK: 'Send Payment Link',
  SEND_REMINDER:     'Send Reminder',
};

function MessageWithLink({ message }) {
  // Extract any URL from the message text
  const urlMatch = message.match(/https?:\/\/[^\s]+/);
  if (!urlMatch) {
    return (
      <p className="mt-2 text-[12px] font-medium text-gray-700 bg-white/60 rounded px-2 py-1.5 leading-relaxed">
        {message}
      </p>
    );
  }
  const url    = urlMatch[0];
  const before = message.slice(0, urlMatch.index).replace(/:\s*$/, '').trim();
  return (
    <div className="mt-2.5 rounded-lg border border-indigo-200 bg-indigo-50 overflow-hidden">
      {before && (
        <p className="px-3 pt-2.5 pb-1 text-[12px] font-medium text-gray-600">{before}</p>
      )}
      <div className="px-3 pb-2.5 flex items-center gap-2">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" strokeWidth="2" strokeLinecap="round" className="flex-shrink-0">
          <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
          <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
        </svg>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[13px] font-bold text-indigo-700 hover:text-indigo-900 underline underline-offset-2 break-all leading-relaxed"
        >
          {url}
        </a>
      </div>
    </div>
  );
}

function fmtAmt(v) {
  if (v == null) return '—';
  return `₹${parseFloat(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function AgentPanel({ caseStatus, agentResult, running, error, onRun, riskAmount }) {
  const [showFactors, setShowFactors] = useState(false);
  const isEligible  = caseStatus === 'OPEN' || caseStatus === 'IN_PROGRESS';
  const r           = agentResult;
  const actionLabel = r ? (ACTION_NAMES[r.action] ?? String(r.action ?? '').replaceAll('_', ' ')) : null;
  const pct         = r ? Math.round((r.confidence ?? 0) * 100) : 0;

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-gray-200 flex items-center gap-2">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2a4 4 0 014 4v1a4 4 0 01-4 4 4 4 0 01-4-4V6a4 4 0 014-4z"/>
          <path d="M8 11c-2.5 0-4.5 1.8-4.5 4 0 1.5.8 2.8 2 3.5"/>
          <path d="M16 11c2.5 0 4.5 1.8 4.5 4 0 1.5-.8 2.8-2 3.5"/>
        </svg>
        <span className="text-[12px] font-extrabold text-gray-600 uppercase tracking-widest">AI Recommendation</span>
      </div>

      <div className="px-5 py-4">
        {/* Not run yet */}
        {!r && !running && (
          <p className="text-[13px] font-medium text-gray-500 leading-relaxed py-2">
            No recommendation yet. Run recovery to get an AI analysis.
          </p>
        )}

        {/* Running */}
        {running && (
          <div className="flex items-center gap-3 text-[14px] text-indigo-600 font-semibold py-3">
            <div className="spinner w-4 h-4" />
            Analyzing customer history…
          </div>
        )}

        {/* Result */}
        {r && !running && (
          <div className="flex flex-col gap-3">
            {/* Decision box */}
            <div className="border border-green-200 bg-green-50 rounded-lg px-4 py-3.5 flex items-start justify-between gap-3">
              <div>
                <div className="text-[28px] font-black text-green-600 tracking-tight leading-none">
                  {r.decision === 'RECOVER' ? 'RECOVER' : r.decision ?? '—'}
                </div>
                {actionLabel && (
                  <>
                    <div className="text-[11px] font-bold text-gray-500 mt-2 uppercase tracking-wider">
                      Recommended Action
                    </div>
                    <div className="text-[16px] font-extrabold text-gray-800 mt-0.5">{actionLabel}</div>
                  </>
                )}
              </div>
              {/* Confidence badge */}
              {r.confidence != null && (
                <span className="flex-shrink-0 inline-flex items-center px-3 py-1 rounded-full text-[12px] font-bold bg-green-100 text-green-700 border border-green-300 whitespace-nowrap">
                  {pct}% Confidence
                </span>
              )}
            </div>

            {/* Reason */}
            {r.reason && (
              <p className="text-[13px] font-medium text-gray-700 leading-relaxed">{r.reason}</p>
            )}

            {/* View reasoning factors toggle */}
            {r.evidence?.length > 0 && (
              <div>
                <button
                  className="w-full flex items-center justify-between text-[13px] font-bold text-gray-500 hover:text-gray-700 py-2 border-t border-gray-200 transition-colors"
                  onClick={() => setShowFactors(v => !v)}
                  aria-expanded={showFactors}
                >
                  <span>View reasoning factors</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                    className={`transition-transform ${showFactors ? 'rotate-180' : ''}`}>
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
                {showFactors && (
                  <div className="mt-2 flex flex-col gap-2">
                    {r.evidence.map((e, i) => (
                      <div key={i} className="flex items-start gap-2 text-[13px] font-medium text-gray-700 leading-relaxed">
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 flex-shrink-0 mt-[7px]" />
                        {e}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Success outcome */}
            {r.action_result?.success && (
              <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 mt-1">
                <div className="flex items-center gap-2 text-[13px] font-bold text-green-700 mb-2.5">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="8" cy="8" r="6"/><polyline points="5 8.5 7 10.5 11 6"/>
                  </svg>
                  Recovery simulated <SimulatedBadge />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: 'Case status',     value: <StatusBadge value={caseStatus} /> },
                    { label: 'Payment outcome', value: <StatusBadge value={r.action_result.payment_outcome} /> },
                    { label: <span className="flex items-center gap-1">Recovered <SimulatedBadge /></span>, value: <span className="text-green-700 font-bold">{fmtAmt(r.recovered_amount)}</span> },
                  ].map((f, i) => (
                    <div key={i}>
                      <div className="text-[11px] font-bold text-gray-500 uppercase tracking-wide mb-1">{f.label}</div>
                      <div className="text-[14px] font-semibold text-gray-800">{f.value}</div>
                    </div>
                  ))}
                </div>
                {r.action_result.message && (
                  <MessageWithLink message={r.action_result.message} />
                )}
                {r.completed_at && (
                  <p className="mt-1.5 text-[11px] font-medium text-gray-500">Completed {fmtDate(r.completed_at)}</p>
                )}
              </div>
            )}

            {/* Failure outcome */}
            {r.action_result && !r.action_result.success && (
              <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-[13px] font-bold text-red-700">
                Recovery did not succeed.
                {r.action_result.message && (
                  <p className="mt-1 text-[12px] font-normal text-red-600 leading-relaxed">
                    {r.action_result.message}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="mt-2 px-4 py-2.5 bg-red-50 border border-red-200 rounded-lg text-[13px] font-semibold text-red-700">
            Recovery could not be started.
          </div>
        )}
      </div>
    </div>
  );
}
