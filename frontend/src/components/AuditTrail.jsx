/**
 * AuditTrail — full history, collapsible beyond the initial preview.
 * Shows first 5 entries by default; "View full audit trail" reveals all.
 */

import { useState } from 'react';

const EVENT_LABELS = {
  agent_started:                  'Agent started',
  case_loaded:                    'Case loaded',
  customer_history_retrieved:     'Customer history retrieved',
  payment_history_retrieved:      'Payment history retrieved',
  recovery_attempts_retrieved:    'Recovery attempts retrieved',
  decision_made:                  'AI recommendation generated',
  policy_checked:                 'Policy checked',
  payment_retry_simulated:        'Payment retry simulated',
  payment_success_simulated:      'Payment success (simulated)',
  payment_failure_simulated:      'Payment failure (simulated)',
  payment_link_simulated:         'Payment link generated (simulated)',
  razorpay_payment_link_created:  'Razorpay payment link created',
  razorpay_payment_link_attached: 'Payment link attached to payment',
  payment_link_sent:              'Payment link sent to customer',
  notification_simulated:         'Reminder notification (simulated)',
  action_selected:                'Recovery action selected',
  case_updated:                   'Case status updated',
  agent_completed:                'Agent completed',
  agent_error:                    'Agent error',
  agent_waiting:                  'Agent waiting',
  recovery_stopped:               'Recovery stopped',
  case_created:                   'Case created',
  action_taken:                   'Recovery action executed',
  action_executed:                'Recovery action executed',
  action_simulated:               'Recovery action simulated',
  history_fetched:                'Customer history analyzed',
};

function labelFor(key) {
  const lower = String(key).toLowerCase();
  return EVENT_LABELS[lower] ?? String(key).replace(/_/g, ' ');
}

function fmtTime(dateStr) {
  const d = new Date(dateStr);
  return isNaN(d) ? '—' : d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

function dotColor(eventType) {
  const key = String(eventType).toLowerCase();
  if (key.includes('error'))                         return 'bg-red-500';
  if (key.includes('sent') || key.includes('link'))  return 'bg-blue-500';
  if (key.includes('success') || key === 'agent_completed') return 'bg-green-500';
  if (key.includes('stopped') || key.includes('failure')) return 'bg-orange-400';
  return 'bg-indigo-500';
}

const PREVIEW_COUNT = 5;

export default function AuditTrail({ audit, loading, error }) {
  const [expanded, setExpanded] = useState(false);

  const entries  = audit?.entries ?? [];
  const hasMore  = entries.length > PREVIEW_COUNT;
  const visible  = expanded ? entries : entries.slice(0, PREVIEW_COUNT);

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round">
            <polyline points="1 8 4 5 7 10 10 4 13 8 16 6"/>
            <line x1="0" y1="20" x2="18" y2="20"/>
          </svg>
          <span className="text-[12px] font-extrabold text-gray-600 uppercase tracking-widest">Audit Timeline</span>
        </div>
        {entries.length > 0 && (
          <span className="text-[11px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full">
            {entries.length}
          </span>
        )}
      </div>

      <div className="px-4 py-3">
        {/* Loading skeleton */}
        {loading && entries.length === 0 && (
          <div className="flex flex-col gap-3 py-1">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="flex items-center gap-3">
                <div className="skeleton h-3 w-12 rounded flex-shrink-0" />
                <div className="skeleton h-3 w-3/4 rounded" />
              </div>
            ))}
          </div>
        )}

        {!loading && error && (
          <p className="text-[13px] font-medium text-red-600 py-2">Couldn&apos;t load audit trail.</p>
        )}

        {!loading && !error && entries.length === 0 && (
          <div className="text-center py-4">
            <p className="text-[13px] font-bold text-gray-600">No activity yet</p>
            <p className="text-[12px] font-medium text-gray-400 mt-0.5">Run recovery to record activity.</p>
          </div>
        )}

        {visible.length > 0 && (
          <div className="flex flex-col mt-1">
            {visible.map((entry, idx) => {
              const isLast = idx === visible.length - 1;
              const color  = dotColor(entry.event_type);
              return (
                <div key={entry.id ?? idx} className="flex items-start gap-3">
                  {/* Time */}
                  <span className="text-[11px] font-semibold text-gray-500 w-16 flex-shrink-0 pt-[3px] tabular-nums leading-snug">
                    {fmtTime(entry.created_at)}
                  </span>
                  {/* Dot + connector line */}
                  <div className="flex flex-col items-center flex-shrink-0">
                    <div className={`w-2.5 h-2.5 rounded-full ${color} mt-[3px] flex-shrink-0`} />
                    {!isLast && <div className="w-px flex-1 bg-gray-200 min-h-[20px]" />}
                  </div>
                  {/* Label */}
                  <p className={`text-[13px] font-semibold text-gray-700 leading-snug ${isLast ? 'pb-0' : 'pb-3'}`}>
                    {labelFor(entry.event_type)}
                  </p>
                </div>
              );
            })}
          </div>
        )}

        {/* Toggle button */}
        {hasMore && (
          <button
            onClick={() => setExpanded(v => !v)}
            className="mt-3 text-[13px] font-bold text-indigo-600 hover:text-indigo-800 hover:underline transition-colors flex items-center gap-1"
          >
            {expanded ? (
              <>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="18 15 12 9 6 15"/>
                </svg>
                Show less
              </>
            ) : (
              <>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
                View full audit trail ({entries.length} events)
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
