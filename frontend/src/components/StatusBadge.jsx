/**
 * StatusBadge — coloured chip for case / decision / action status values.
 */
export default function StatusBadge({ value }) {
  if (!value) return null;
  const key = value.toLowerCase();
  return <span className={`chip chip-${key}`}>{value}</span>;
}
