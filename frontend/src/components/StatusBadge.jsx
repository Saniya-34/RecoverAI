/**
 * StatusBadge — coloured chip with merchant-friendly labels.
 */

// Local label definitions (fallback if utils/format.js is missing)
const ACTION_LABELS = {
  RETRY_PAYMENT: "Retry Payment",
  SEND_PAYMENT_LINK: "Send Payment Link",
  SEND_REMINDER: "Send Reminder",
};
const DECISION_LABELS = {
  RECOVER: "Recover",
  NOT_RECOVERED: "Not Recovered",
};
const STATUS_LABELS = {
  OPEN: "Open",
  IN_PROGRESS: "In Progress",
  RECOVERED: "Recovered",
  STOPPED: "Stopped",
  NOT_RECOVERED: "Not Recovered",
};

const ALL_LABELS = { ...STATUS_LABELS, ...DECISION_LABELS, ...ACTION_LABELS };

export default function StatusBadge({ value }) {
  if (!value) return null;
  const key = String(value).toLowerCase();
  const label = ALL_LABELS[value] ?? String(value).replaceAll('_', ' ');
  return <span className={`chip chip-${key}`}>{label}</span>;
}
