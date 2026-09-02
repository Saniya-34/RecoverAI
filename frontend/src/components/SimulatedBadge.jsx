import { IS_SIMULATED } from '../config.js';

export default function SimulatedBadge() {
  if (!IS_SIMULATED) return null;
  return (
    <span
      title="Simulated demo — no real payments"
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold tracking-[0.4px] uppercase bg-violet-50 border border-violet-200 text-violet-700 align-middle"
    >
      Demo
    </span>
  );
}
