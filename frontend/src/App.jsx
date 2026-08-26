/**
 * RecoverAI Dashboard — Main App
 *
 * All data comes from the FastAPI backend.
 * Gemini API key is never exposed to the browser.
 * Simulated actions are clearly labelled — no real money is moved.
 */

import { useState, useEffect, useCallback } from 'react';
import './dashboard.css';

import {
  getHealth,
  getDashboardSummary,
  getRecoveryCases,
  getRecoveryCase,
  getRecoveryAudit,
  runRecoveryAgent,
  getCustomerHistory,
} from './services/api.js';

import SummaryCards from './components/SummaryCards.jsx';
import CaseList     from './components/CaseList.jsx';
import CaseDetail   from './components/CaseDetail.jsx';
import AgentPanel   from './components/AgentPanel.jsx';
import AuditTrail   from './components/AuditTrail.jsx';

// ──────────────────────────────────────────────────────────────────────────────

export default function App() {
  // ── Backend status ──────────────────────────────────────────────────────────
  const [backendOnline, setBackendOnline] = useState(null); // null=checking

  // ── Dashboard summary ───────────────────────────────────────────────────────
  const [summary, setSummary]           = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState(null);

  // ── Case list ───────────────────────────────────────────────────────────────
  const [cases, setCases]               = useState([]);
  const [casesLoading, setCasesLoading] = useState(true);
  const [casesError, setCasesError]     = useState(null);
  const [statusFilter, setStatusFilter] = useState('');

  // ── Selected case ───────────────────────────────────────────────────────────
  const [selectedId, setSelectedId]         = useState(null);
  const [caseDetail, setCaseDetail]         = useState(null);
  const [caseDetailLoading, setCaseDetailLoading] = useState(false);
  const [caseDetailError, setCaseDetailError]     = useState(null);

  // ── Customer history ────────────────────────────────────────────────────────
  const [customerHistory, setCustomerHistory]           = useState(null);
  const [customerHistoryLoading, setCustomerHistoryLoading] = useState(false);
  const [customerHistoryError, setCustomerHistoryError]     = useState(null);

  // ── Audit trail ─────────────────────────────────────────────────────────────
  const [audit, setAudit]             = useState(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError]   = useState(null);

  // ── Agent ───────────────────────────────────────────────────────────────────
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentResult, setAgentResult]   = useState(null);
  const [agentError, setAgentError]     = useState(null);

  // ── Health check ────────────────────────────────────────────────────────────
  useEffect(() => {
    getHealth()
      .then(() => setBackendOnline(true))
      .catch(() => setBackendOnline(false));
  }, []);

  // ── Load summary ────────────────────────────────────────────────────────────
  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      setSummary(await getDashboardSummary());
    } catch (e) {
      setSummaryError(e.message);
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  // ── Load case list ───────────────────────────────────────────────────────────
  const loadCases = useCallback(async (filter = '') => {
    setCasesLoading(true);
    setCasesError(null);
    try {
      const data = await getRecoveryCases({ status: filter || undefined, limit: 100 });
      setCases(data.cases ?? []);
    } catch (e) {
      setCasesError(e.message);
    } finally {
      setCasesLoading(false);
    }
  }, []);

  // ── Load case detail ─────────────────────────────────────────────────────────
  const loadCaseDetail = useCallback(async (id) => {
    setCaseDetailLoading(true);
    setCaseDetailError(null);
    setCaseDetail(null);
    setAgentResult(null);
    setAgentError(null);
    try {
      setCaseDetail(await getRecoveryCase(id));
    } catch (e) {
      setCaseDetailError(e.message);
    } finally {
      setCaseDetailLoading(false);
    }
  }, []);

  // ── Load customer history ───────────────────────────────────────────────────
  const loadCustomerHistory = useCallback(async (id) => {
    setCustomerHistoryLoading(true);
    setCustomerHistoryError(null);
    setCustomerHistory(null);
    try {
      setCustomerHistory(await getCustomerHistory(id));
    } catch (e) {
      setCustomerHistoryError(e.message);
    } finally {
      setCustomerHistoryLoading(false);
    }
  }, []);

  // ── Load audit ───────────────────────────────────────────────────────────────
  const loadAudit = useCallback(async (id) => {
    setAuditLoading(true);
    setAuditError(null);
    try {
      setAudit(await getRecoveryAudit(id));
    } catch (e) {
      setAuditError(e.message);
    } finally {
      setAuditLoading(false);
    }
  }, []);

  // ── Initial load ─────────────────────────────────────────────────────────────
  useEffect(() => {
    loadSummary();
    loadCases(statusFilter);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Filter change ─────────────────────────────────────────────────────────────
  const handleFilterChange = (val) => {
    setStatusFilter(val);
    loadCases(val);
  };

  // ── Select case ───────────────────────────────────────────────────────────────
  const handleSelectCase = (id) => {
    setSelectedId(id);
    loadCaseDetail(id);
    loadAudit(id);
    loadCustomerHistory(id);
  };

  // ── Run agent ─────────────────────────────────────────────────────────────────
  const handleRunAgent = async () => {
    if (!selectedId || agentRunning) return;
    setAgentRunning(true);
    setAgentResult(null);
    setAgentError(null);
    try {
      const result = await runRecoveryAgent(selectedId);
      setAgentResult(result);
      // Refresh everything that changed
      await Promise.all([
        loadSummary(),
        loadCases(statusFilter),
        loadCaseDetail(selectedId),
        loadAudit(selectedId),
        loadCustomerHistory(selectedId),
      ]);
    } catch (e) {
      setAgentError(e.message);
    } finally {
      setAgentRunning(false);
    }
  };

  // ────────────────────────────────────────────────────────────────────────────
  return (
    <div className="dashboard-layout">

      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-header-brand">
          <div className="app-header-logo">R</div>
          <div>
            <div className="app-header-title">RecoverAI</div>
            <div className="app-header-subtitle">
              AI-powered revenue recovery for merchants
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {backendOnline === null && (
            <span className="status-badge" style={{ background: 'var(--code-bg)' }}>
              <span className="status-dot" style={{ background: 'var(--text)' }} />
              Checking…
            </span>
          )}
          {backendOnline === true && (
            <span className="status-badge online">
              <span className="status-dot" /> Backend online
            </span>
          )}
          {backendOnline === false && (
            <span className="status-badge offline">
              <span className="status-dot" /> Backend unavailable
            </span>
          )}
        </div>
      </header>

      {backendOnline === false && (
        <div className="error-banner" style={{ margin: '12px 28px', fontSize: 14 }}>
          ⚠ Backend unavailable. Start the FastAPI server on port 8000.
        </div>
      )}

      {/* ── Summary ── */}
      <SummaryCards
        summary={summary}
        loading={summaryLoading}
        error={summaryError}
      />

      {/* ── Main content ── */}
      <div className="dashboard-main">

        {/* ── Sidebar — case list ── */}
        <CaseList
          cases={cases}
          loading={casesLoading}
          error={casesError}
          selectedId={selectedId}
          onSelect={handleSelectCase}
          statusFilter={statusFilter}
          onStatusFilterChange={handleFilterChange}
        />

        {/* ── Main panel — case detail + agent ── */}
        <div className="main-panel">
          {!selectedId ? (
            <div className="no-selection">
              <div className="no-selection-icon">🔍</div>
              <div className="no-selection-title">Select a recovery case</div>
              <div className="no-selection-desc">
                Choose a case from the left panel to view its details,
                run the AI recovery agent, and see the audit history.
              </div>
            </div>
          ) : (
            <>
              <CaseDetail
                caseData={caseDetail}
                loading={caseDetailLoading}
                error={caseDetailError}
                customerHistory={customerHistory}
                historyLoading={customerHistoryLoading}
                historyError={customerHistoryError}
              />

              <AgentPanel
                caseStatus={caseDetail?.status}
                agentResult={agentResult}
                running={agentRunning}
                error={agentError}
                onRun={handleRunAgent}
              />

              <AuditTrail
                audit={audit}
                loading={auditLoading}
                error={auditError}
              />
            </>
          )}
        </div>

      </div>
    </div>
  );
}
