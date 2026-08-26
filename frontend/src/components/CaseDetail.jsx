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

export default function CaseDetail({ caseData, loading, error, customerHistory, historyLoading, historyError }) {
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

      {/* ── Customer History ── */}
      {(historyLoading || historyError || customerHistory) && (
        <div className="detail-section">
          <p className="detail-section-title">Customer History</p>
          {historyLoading && (
            <div className="loading-row">
              <div className="spinner" /> Loading customer history…
            </div>
          )}
          {historyError && (
            <div className="error-banner">
              Failed to load customer history: {historyError}
            </div>
          )}
          {customerHistory && (
            <>
              <div className="detail-grid" style={{ marginBottom: 20 }}>
                <div className="detail-field">
                  <span className="detail-label">Total Payment Attempts</span>
                  <span className="detail-value">{customerHistory.total_payment_attempts}</span>
                </div>
                <div className="detail-field">
                  <span className="detail-label">Successful Payments</span>
                  <span className="detail-value" style={{ color: '#16a34a', fontWeight: '600' }}>
                    {customerHistory.successful_payments}
                  </span>
                </div>
                <div className="detail-field">
                  <span className="detail-label">Failed Payments</span>
                  <span className="detail-value" style={{ color: '#dc2626', fontWeight: '600' }}>
                    {customerHistory.failed_payments}
                  </span>
                </div>
                <div className="detail-field">
                  <span className="detail-label">Success Rate</span>
                  <span className="detail-value">
                    {(customerHistory.success_rate * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="detail-field">
                  <span className="detail-label">Previous Recovery Attempts</span>
                  <span className="detail-value">{customerHistory.previous_recovery_attempts}</span>
                </div>
              </div>

              <div className="payment-history-list" style={{ marginTop: 18 }}>
                <span className="detail-label" style={{ display: 'block', marginBottom: 10 }}>
                  Previous Payments
                </span>
                {customerHistory.payments && customerHistory.payments.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {customerHistory.payments.map((p, idx) => (
                      <div
                        key={p.id || idx}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '10px 14px',
                          background: 'var(--code-bg)',
                          borderRadius: 8,
                          fontSize: 13,
                          border: '1px solid var(--border)',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                          <span style={{ fontWeight: 600, color: 'var(--text-h)' }}>
                            {fmtAmount(p.amount, p.currency)}
                          </span>
                          <span style={{ fontSize: 11, color: 'var(--text)' }}>
                            {p.attempted_at ? fmtDate(p.attempted_at) : fmtDate(p.created_at)}
                          </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          {p.failure_reason && (
                            <span style={{ fontSize: 11, color: 'var(--text)', fontStyle: 'italic' }}>
                              {p.failure_reason}
                            </span>
                          )}
                          <StatusBadge value={p.status} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: 'var(--text)', fontStyle: 'italic', padding: '10px 0' }}>
                    No previous payments found for this customer.
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
