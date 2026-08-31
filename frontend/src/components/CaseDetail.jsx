/**
 * CaseDetail — merchant-facing case workspace (right-hand panel).
 */

import StatusBadge from './StatusBadge.jsx';
import AgentPanel from './AgentPanel.jsx';
import AuditTrail from './AuditTrail.jsx';
import SimulatedBadge from './SimulatedBadge.jsx';

const TYPE_LABELS = {
  PAYMENT_FAILURE: 'Failed payment',
  CHECKOUT_ABANDONMENT: 'Abandoned checkout',
  SUBSCRIPTION_FAILURE: 'Failed subscription',
  OTHER: 'Other',
};

function customerName(customer) {
  if (!customer) return 'Unknown Customer';
  return customer.name || customer.external_customer_id || 'Unknown Customer';
}

function fmtAmount(v) {
  if (v == null) return '—';
  return `₹${parseFloat(v).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function fmtPct(v) {
  if (v == null) return '—';
  return `${(parseFloat(v) * 100).toFixed(1)}%`;
}

function Field({ label, value, cls = '' }) {
  return (
    <div className="detail-field">
      <span className="detail-label">{label}</span>
      <span className={`detail-value ${cls}`}>{value ?? '—'}</span>
    </div>
  );
}

function Section({ title, children, extra }) {
  return (
    <section className="detail-section">
      <div className="detail-section-heading">
        <h2 className="detail-section-title">{title}</h2>
        {extra}
      </div>
      {children}
    </section>
  );
}

export default function CaseDetail({
  caseData,
  loading,
  error,
  customerHistory,
  historyLoading,
  historyError,
  caseStatus,
  agentResult,
  agentRunning,
  agentError,
  onRunAgent,
  audit,
  auditLoading,
  auditError,
  onBack,
}) {
  if (loading && !caseData) {
    return (
      <div className="detail-section">
        <div className="loading-row">
          <div className="spinner" /> Loading case…
        </div>
      </div>
    );
  }

  if (error && !caseData) {
    return (
      <div className="detail-section">
        <div className="error-banner">Could not load this case: {error}</div>
      </div>
    );
  }

  if (!caseData) return null;

  const { customer, order, payment } = caseData;
  const recovered = parseFloat(caseData.recovered_amount) > 0;
  const historyReady = Boolean(customerHistory) && !historyLoading;

  return (
    <>
      <div className="detail-sticky-bar">
        {onBack && (
          <button type="button" className="btn-back" onClick={onBack}>
            ← Cases
          </button>
        )}
        <div className="detail-sticky-identity">
          <div className="detail-sticky-name">{customerName(customer)}</div>
          <div className="detail-sticky-meta">
            {customer?.email || 'No email on file'}
          </div>
        </div>
        <StatusBadge value={caseData.status} />
      </div>

      {error && (
        <div className="error-banner" style={{ margin: '12px 20px 0' }}>
          Could not refresh this case: {error}
        </div>
      )}

      <div className="highlight-strip">
        <div className="highlight-item">
          <span className="detail-label">At risk</span>
          <span className="highlight-value accent">{fmtAmount(caseData.risk_amount)}</span>
        </div>
        <div className="highlight-item">
          <span className="detail-label" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            Recovered <SimulatedBadge />
          </span>
          <span className={`highlight-value ${recovered ? 'success' : ''}`}>
            {fmtAmount(caseData.recovered_amount)}
          </span>
        </div>
        <div className="highlight-item">
          <span className="detail-label">Why it failed</span>
          <span className="highlight-value wrap">
            {payment?.failure_reason || 'No failure reason recorded'}
          </span>
        </div>
        <div className="highlight-item">
          <span className="detail-label">Payment success rate</span>
          <span className="highlight-value">
            {historyLoading ? '…' : historyReady ? fmtPct(customerHistory.success_rate) : '—'}
          </span>
        </div>
        <div className="highlight-item">
          <span className="detail-label">AI decision</span>
          <span className="highlight-value">
            {agentResult ? <StatusBadge value={agentResult.decision} /> : 'Not analyzed yet'}
          </span>
        </div>
        <div className="highlight-item">
          <span className="detail-label">Recommended action</span>
          <span className="highlight-value">
            {agentResult ? <StatusBadge value={agentResult.action} /> : '—'}
          </span>
        </div>
      </div>

      <Section title="Case overview" extra={<StatusBadge value={caseData.status} />}>
        <div className="detail-grid">
          <Field label="What happened" value={TYPE_LABELS[caseData.case_type] ?? caseData.case_type} />
          <Field label="Found on" value={fmtDate(caseData.detected_at)} />
          <Field
            label="Closed on"
            value={caseData.resolved_at ? fmtDate(caseData.resolved_at) : 'Still open'}
          />
        </div>
        <p className="case-explanation">
          {caseData.status === 'RECOVERED'
            ? 'Payment successfully recovered. Case has been recovered.'
            : caseData.explanation}
        </p>
      </Section>

      <Section title="Customer">
        {customer ? (
          <div className="detail-grid">
            <Field label="Name" value={customer.name || '—'} />
            <Field label="Email" value={customer.email || '—'} />
          </div>
        ) : (
          <p className="muted-copy">No customer details on this case.</p>
        )}
      </Section>

      <Section title="Order & payment">
        <div className="detail-grid">
          {order && (
            <>
              <Field label="Order amount" value={fmtAmount(order.amount)} />
              <div className="detail-field">
                <span className="detail-label">Order status</span>
                <span className="detail-value">
                  <StatusBadge value={order.status} />
                </span>
              </div>
            </>
          )}
          {payment ? (
            <>
              <Field label="Payment amount" value={fmtAmount(payment.amount)} />
              <div className="detail-field">
                <span className="detail-label">Payment status</span>
                <span className="detail-value">
                  <StatusBadge value={payment.status} />
                </span>
              </div>
              <Field label="Payment method" value={payment.payment_method || '—'} />
              <Field
                label="Failure reason"
                value={payment.failure_reason || 'Not recorded'}
              />
            </>
          ) : (
            <p className="muted-copy">No payment attempt is attached to this case.</p>
          )}
        </div>
      </Section>

      <Section title="Customer payment history">
        {historyLoading && (
          <div className="loading-row">
            <div className="spinner" /> Loading payment history…
          </div>
        )}
        {historyError && (
          <div className="error-banner">Could not load payment history: {historyError}</div>
        )}
        {customerHistory && !historyLoading && (
          <>
            <div className="detail-grid" style={{ marginBottom: 16 }}>
              <Field label="Attempts" value={customerHistory.total_payment_attempts} />
              <Field label="Succeeded" value={customerHistory.successful_payments} />
              <Field label="Failed" value={customerHistory.failed_payments} />
              <Field label="Success rate" value={fmtPct(customerHistory.success_rate)} />
              <Field
                label="Past recovery tries"
                value={customerHistory.previous_recovery_attempts}
              />
            </div>
            {customerHistory.payments?.length > 0 ? (
              <div className="payment-history-list">
                {customerHistory.payments.map((p, idx) => (
                  <div key={p.id || idx} className="payment-history-row">
                    <div>
                      <div className="payment-history-amount">{fmtAmount(p.amount)}</div>
                      <div className="payment-history-date">
                        {fmtDate(p.attempted_at || p.created_at)}
                      </div>
                    </div>
                    <div className="payment-history-right">
                      {p.failure_reason && (
                        <span className="payment-history-reason">{p.failure_reason}</span>
                      )}
                      <StatusBadge value={p.status} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted-copy">No previous payments for this customer.</p>
            )}
          </>
        )}
      </Section>

      <AgentPanel
        caseStatus={caseStatus ?? caseData.status}
        agentResult={agentResult}
        running={agentRunning}
        error={agentError}
        onRun={onRunAgent}
      />

      <AuditTrail audit={audit} loading={auditLoading} error={auditError} />
    </>
  );
}
