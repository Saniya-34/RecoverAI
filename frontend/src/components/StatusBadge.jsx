/**
 * StatusBadge — Tailwind-based status chip.
 */

const LABELS = {
  OPEN: 'Open', IN_PROGRESS: 'In Progress', RECOVERED: 'Recovered',
  STOPPED: 'Stopped', NOT_RECOVERED: 'Not Recovered', RECOVER: 'Recover',
  RETRY_PAYMENT: 'Retry Payment', SEND_PAYMENT_LINK: 'Send Link', SEND_REMINDER: 'Send Reminder',
  SUCCESS: 'Success', FAILED: 'Failed', PENDING: 'Pending',
  CANCELLED: 'Cancelled', PAID: 'Paid', UNPAID: 'Unpaid', WAIT: 'Wait', STOP: 'Stop',
};

const STYLES = {
  open:              'bg-amber-50  text-[#c96c00] border-orange-200',
  in_progress:       'bg-sky-50    text-[#0369a1] border-sky-200',
  recovered:         'bg-green-50  text-[#15803d] border-green-200',
  stopped:           'bg-red-50    text-[#b91c1c] border-red-200',
  not_recovered:     'bg-gray-50   text-gray-500  border-gray-300',
  recover:           'bg-green-50  text-[#15803d] border-green-200',
  wait:              'bg-amber-50  text-[#c96c00] border-orange-200',
  stop:              'bg-red-50    text-[#b91c1c] border-red-200',
  retry_payment:     'bg-indigo-50 text-[#3f3fe8] border-indigo-200',
  send_payment_link: 'bg-indigo-50 text-[#3f3fe8] border-indigo-200',
  send_reminder:     'bg-indigo-50 text-[#3f3fe8] border-indigo-200',
  success:           'bg-green-50  text-[#15803d] border-green-200',
  failed:            'bg-red-50    text-[#b91c1c] border-red-200',
  pending:           'bg-amber-50  text-[#c96c00] border-orange-200',
  cancelled:         'bg-gray-50   text-gray-500  border-gray-300',
  paid:              'bg-green-50  text-[#15803d] border-green-200',
  unpaid:            'bg-red-50    text-[#b91c1c] border-red-200',
};

export default function StatusBadge({ value }) {
  if (!value) return null;
  const key   = String(value).toLowerCase().replace(/\s+/g, '_');
  const label = LABELS[String(value).toUpperCase()] ?? LABELS[value] ?? String(value).replaceAll('_', ' ');
  const style = STYLES[key] ?? 'bg-gray-50 text-gray-500 border-gray-300';
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-[12px] font-bold border whitespace-nowrap leading-[1.5] ${style}`}>
      {label}
    </span>
  );
}
