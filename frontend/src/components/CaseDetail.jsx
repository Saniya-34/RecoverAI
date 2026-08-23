/**
 * CaseDetail — full case information panel with customer/order/payment context.
 */

import StatusBadge from './StatusBadge.jsx';

function Field({ label, value, cls = '' }) {
  return (
    <div className="detail-field">
      <span className="detail-label">{label}</span>
      <span className={`detail-value ${cls}`}>{value ?? '—'}</span>
    </div>
  );
}

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function fmtAmount(v, currency = 'INR') {
  if (v == null) return '—';
  return `₹${parseFloat(v).toLocaleString('en-IN', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

const TYPE_LABELS = {
  PAYMENT_FAILURE:      'Payment Failure',
  CHECKOUT_ABANDONMENT: 'Checkout Abandonment',
  SUBSCRIPTION_FAILURE: 'Subscription Failure',
  OTHER:                'Other',
};

export default function CaseDetail({ caseData, loading, error }) {
  if (loading) {
    return (
      <div className="detail-section">
        <div className="loading-row"><div className="spinner" /> Loading case…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="detail-section">
        <div className="error-banner">Failed to load case: {error}</div>
      </div>
    );
  }

  if (!caseData) return null;

  const { customer, order, payment } = caseData;

  return (
    <>
      {/* ── Risk Overview ── */}
      <div className="detail-section">
        <p className="detail-section-title">
          Case #{caseData.id}
          <StatusBadge value={caseData.status} />
        </p>
        <div className="detail-grid">
          <div className="detail-field">
            <span className="detail-label">Risk Amount</span>
            <span className="detail-value amount">{fmtAmount(caseData.risk_amount)}</span>
          </div>
          <Field label="Case Type"   value={TYPE_LABELS[caseData.case_type] ?? caseData.case_type} />
          <Field label="Detected At" value={fmtDate(caseData.detected_at)} />
          <Field label="Resolved At" value={caseData.resolved_at ? fmtDate(caseData.resolved_at) : 'Not yet'} />
        </div>

        {caseData.explanation && (
          <div style={{ marginTop: 14, padding: '10px 12px', background: 'var(--accent-bg)',
            border: '1px solid var(--accent-border)', borderRadius: 8,
            fontSize: 13, color: 'var(--text-h)', lineHeight: 1.5 }}>
            {caseData.explanation}
          </div>
        )}
      </div>

      {/* ── Customer ── */}
      {customer && (
        <div className="detail-section">
          <p className="detail-section-title">Customer</p>
          <div className="detail-grid">
            <Field label="Name"       value={customer.name} />
            <Field label="Email"      value={customer.email} />
            <Field label="Customer ID" value={customer.external_customer_id} cls="mono" />
          </div>
        </div>
      )}

      {/* ── Order ── */}
      {order && (
        <div className="detail-section">
          <p className="detail-section-title">Order</p>
          <div className="detail-grid">
            <Field label="Order ID"  value={order.external_order_id} cls="mono" />
            <Field label="Amount"    value={fmtAmount(order.amount)} />
            <div className="detail-field">
              <span className="detail-label">Status</span>
              <span className="detail-value"><StatusBadge value={order.status} /></span>
            </div>
            <Field label="Currency"  value={order.currency} />
          </div>
        </div>
      )}

      {/* ── Payment ── */}
      {payment && (
        <div className="detail-section">
          <p className="detail-section-title">Payment Attempt</p>
          <div className="detail-grid">
            <Field label="Payment ID"    value={payment.external_payment_id} cls="mono" />
            <Field label="Amount"        value={fmtAmount(payment.amount)} />
            <div className="detail-field">
              <span className="detail-label">Status</span>
              <span className="detail-value"><StatusBadge value={payment.status} /></span>
            </div>
            <Field label="Method"        value={payment.payment_method} />
            <Field label="Failure Reason" value={payment.failure_reason} />
          </div>
        </div>
      )}
    </>
  );
}
