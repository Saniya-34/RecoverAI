/**
 * AuditTrail — always-visible compact timeline matching reference image.
 * Time on left, dot + label on right, "View full audit trail" link at bottom.
 */

const EVENT_LABELS = {
  case_created:     'Case created',
  decision_made:    'AI recommendation generated',
  action_taken:     'Recovery action executed',
  agent_started:    'Agent started',
  history_fetched:  'Customer history analyzed',
  policy_checked:   'Policy checked',
  action_executed:  'Recovery action executed',
  action_simulated: 'Recovery action simulated',
  case_updated:     'Case status updated',
};

function labelFor(key) {
  return EVENT_LABELS[key] ?? String(key).replace(/_/g, ' ');
}
function fmtTime(dateStr) {
  const d = new Date(dateStr);
  return isNaN(d) ? '—' : d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

export default function AuditTrail({ audit, loading, error }) {
  const entries = audit?.entries ?? [];
  const visible = entries.slice(0, 5);

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-gray-200 flex items-center gap-2">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round">
          <polyline points="1 8 4 5 7 10 10 4 13 8 16 6"/>
          <line x1="0" y1="20" x2="18" y2="20"/>
        </svg>
        <span className="text-[12px] font-extrabold text-gray-600 uppercase tracking-widest">Audit Timeline</span>
      </div>

      <div className="px-4 py-3">
        {loading && entries.length === 0 && (
          <div className="flex flex-col gap-3 py-1">
            {[1,2,3].map(i => (
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
              return (
                <div key={entry.id ?? idx} className="flex items-start gap-3">
                  {/* Time */}
                  <span className="text-[11px] font-semibold text-gray-500 w-16 flex-shrink-0 pt-[3px] tabular-nums">
                    {fmtTime(entry.created_at)}
                  </span>
                  {/* Dot + line */}
                  <div className="flex flex-col items-center flex-shrink-0">
                    <div className="w-2.5 h-2.5 rounded-full bg-indigo-500 mt-[3px] flex-shrink-0" />
                    {!isLast && <div className="w-px flex-1 bg-gray-200 min-h-[20px]" />}
                  </div>
                  {/* Label */}
                  <p className={`text-[13px] font-semibold text-gray-700 ${isLast ? 'pb-0' : 'pb-3'} leading-snug`}>
                    {labelFor(entry.event_type)}
                  </p>
                </div>
              );
            })}
          </div>
        )}

        {entries.length > 0 && (
          <button className="mt-3 text-[13px] font-bold text-indigo-600 hover:text-indigo-800 hover:underline transition-colors">
            View full audit trail
          </button>
        )}
      </div>
    </div>
  );
}
