import { IS_SIMULATED } from '../config.js';
import './SimulatedBadge.css';

export default function SimulatedBadge() {
  if (!IS_SIMULATED) return null;
  return (
    <span className="simulated-badge" title="This data is from a simulation / demo environment">
      DEMO / SIMULATED
    </span>
  );
}
