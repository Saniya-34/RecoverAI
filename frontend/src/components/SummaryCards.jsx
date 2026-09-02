/**
 * SummaryCards — icon left, label + big value + sub-text. No sparklines.
 */

function fmt(v) {
  if (v == null) return '—';
  const n = parseFloat(v);
  if (n >= 100000) return `₹${(n / 100000).toFixed(1)}L`;
  if (n >= 1000)   return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n.toFixed(0)}`;
}

const CARDS = [
  {
    id: 'risk',
    label: 'REVENUE AT RISK',
    iconBg: 'bg-orange-50',
    iconColor: 'text-orange-500',
    valueColor: 'text-orange-600',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <line x1="12" y1="1" x2="12" y2="23"/>
        <path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>
      </svg>
    ),
  },
  {
    id: 'open',
    label: 'OPEN CASES',
    iconBg: 'bg-blue-50',
    iconColor: 'text-blue-500',
    valueColor: 'text-blue-700',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <rect x="2" y="7" width="20" height="14" rx="2"/>
        <path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/>
      </svg>
    ),
  },
  {
    id: 'progress',
    label: 'IN PROGRESS',
    iconBg: 'bg-purple-50',
    iconColor: 'text-purple-500',
    valueColor: 'text-purple-700',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M5 3l14 9-14 9V3z"/>
      </svg>
    ),
  },
  {
    id: 'recovered',
    label: 'RECOVERED',
    iconBg: 'bg-green-50',
    iconColor: 'text-green-600',
    valueColor: 'text-green-700',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
        <polyline points="22 4 12 14.01 9 11.01"/>
      </svg>
    ),
  },
];

function SkeletonCard() {
  return (
    <div className="bg-white border border-gray-100 rounded-xl px-5 py-4 shadow-sm flex items-center gap-4">
      <div className="skeleton w-12 h-12 rounded-xl flex-shrink-0" />
      <div className="flex-1">
        <div className="skeleton h-3 w-2/5 rounded mb-3" />
        <div className="skeleton h-9 w-2/5 rounded mb-2" />
        <div className="skeleton h-3 w-3/5 rounded" />
      </div>
    </div>
  );
}

export default function SummaryCards({ summary, loading, error }) {
  if (loading) {
    return (
      <div className="bg-white border-b border-gray-100 px-6 py-3 flex-shrink-0">
        <div className="grid grid-cols-4 gap-4">
          <SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard />
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="bg-white border-b border-gray-100 px-6 py-3 flex-shrink-0">
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          Couldn&apos;t load overview.
        </div>
      </div>
    );
  }

  const s = summary || {};
  const values = [
    { value: fmt(s.total_revenue_at_risk), sub: `${s.open_cases ?? '—'} open · ${s.in_progress_cases ?? '—'} in progress` },
    { value: s.open_cases ?? '—',          sub: `of ${s.total_cases ?? '—'} total` },
    { value: s.in_progress_cases ?? '—',   sub: 'Being recovered' },
    { value: fmt(s.recovered_revenue),     sub: 'Recovered revenue' },
  ];

  return (
    <div className="bg-white border-b border-gray-100 px-6 py-3 flex-shrink-0">
      <div className="grid grid-cols-4 gap-4">
        {CARDS.map((card, i) => (
          <div key={card.id}
            className="bg-white border border-gray-100 rounded-xl px-5 py-4 shadow-sm hover:shadow-md transition-shadow flex items-center gap-4">
            {/* Icon */}
            <div className={`w-12 h-12 rounded-xl flex-shrink-0 flex items-center justify-center ${card.iconBg} ${card.iconColor}`}>
              {card.icon}
            </div>
            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="text-[11px] font-bold text-gray-500 tracking-widest uppercase mb-0.5">{card.label}</div>
              <div className={`text-[32px] font-black tracking-tight leading-none ${card.valueColor} mb-1.5`}>
                {values[i].value}
              </div>
              <div className="text-[12px] font-medium text-gray-500">{values[i].sub}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
