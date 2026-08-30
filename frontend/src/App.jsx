/**
 * RecoverAI Dashboard — Main App
 *
 * All data comes from the FastAPI backend.
 * Gemini API key is never exposed to the browser.
 * Simulated actions are clearly labelled — no real money is moved.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
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
import CaseList from './components/CaseList.jsx';
import CaseDetail from './components/CaseDetail.jsx';

export default function App() {
  const [backendOnline, setBackendOnline] = useState(null);

  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState(null);

  const [cases, setCases] = useState([]);
  const [casesLoading, setCasesLoading] = useState(true);
  const [casesError, setCasesError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');

  const [selectedId, setSelectedId] = useState(null);
  const [caseDetail, setCaseDetail] = useState(null);
  const [caseDetailLoading, setCaseDetailLoading] = useState(false);
  const [caseDetailError, setCaseDetailError] = useState(null);

  const [customerHistory, setCustomerHistory] = useState(null);
  const [customerHistoryLoading, setCustomerHistoryLoading] = useState(false);
  const [customerHistoryError, setCustomerHistoryError] = useState(null);

  const [audit, setAudit] = useState(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState(null);

  const [agentRunning, setAgentRunning] = useState(false);
  const [agentResult, setAgentResult] = useState(null);
  const [agentError, setAgentError] = useState(null);

  const [mobileShowDetail, setMobileShowDetail] = useState(false);
  const detailPanelRef = useRef(null);

  useEffect(() => {
    getHealth()
      .then(() => setBackendOnline(true))
      .catch(() => setBackendOnline(false));
  }, []);

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

  const loadCases = useCallback(async (status = '', type = '') => {
    setCasesLoading(true);
    setCasesError(null);
    try {
      const data = await getRecoveryCases({
        status: status || undefined,
        type: type || undefined,
        limit: 100,
      });
      setCases(data.cases ?? []);
    } catch (e) {
      setCasesError(e.message);
    } finally {
      setCasesLoading(false);
    }
  }, []);

  const loadCaseDetail = useCallback(async (id) => {
    setCaseDetailLoading(true);
    setCaseDetailError(null);
    setCaseDetail(null);
    try {
      setCaseDetail(await getRecoveryCase(id));
    } catch (e) {
      setCaseDetailError(e.message);
    } finally {
      setCaseDetailLoading(false);
    }
  }, []);

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

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadSummary();
    loadCases(statusFilter, typeFilter);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFilterChange = (val) => {
    setStatusFilter(val);
    loadCases(val, typeFilter);
  };

  const handleTypeFilterChange = (val) => {
    setTypeFilter(val);
    loadCases(statusFilter, val);
  };

  const handleSelectCase = (id) => {
    setSelectedId(id);
    setCaseDetail(null);
    setAgentResult(null);
    setAgentError(null);
    setAudit(null);
    setCustomerHistory(null);
    setMobileShowDetail(true);
    loadCaseDetail(id);
    loadAudit(id);
    loadCustomerHistory(id);
  };

  useEffect(() => {
    if (detailPanelRef.current) {
      detailPanelRef.current.scrollTop = 0;
    }
  }, [selectedId]);

  const handleRunAgent = async () => {
    if (!selectedId || agentRunning) return;
    setAgentRunning(true);
    setAgentResult(null);
    setAgentError(null);
    try {
      const result = await runRecoveryAgent(selectedId);
      setAgentResult(result);
      await Promise.all([
        loadSummary(),
        loadCases(statusFilter, typeFilter),
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

  return (
    <div className="dashboard-layout">
      <header className="app-header">
        <div className="app-header-brand">
          <div className="app-header-logo">R</div>
          <div>
            <div className="app-header-title">RecoverAI</div>
            <div className="app-header-subtitle">
              Recover failed payments and abandoned checkouts
            </div>
          </div>
        </div>

        <div className="header-status">
          {backendOnline === null && (
            <span className="status-badge">
              <span className="status-dot" style={{ background: 'var(--text)' }} />
              Connecting…
            </span>
          )}
          {backendOnline === true && (
            <span className="status-badge online">
              <span className="status-dot" /> Connected
            </span>
          )}
          {backendOnline === false && (
            <span className="status-badge offline">
              <span className="status-dot" /> Can&apos;t connect
            </span>
          )}
        </div>
      </header>

      {backendOnline === false && (
        <div className="error-banner" style={{ margin: '8px 20px 0', flexShrink: 0 }}>
          The recovery service is unavailable. Start the server on port 8000 and refresh.
        </div>
      )}

      <SummaryCards
        summary={summary}
        loading={summaryLoading}
        error={summaryError}
      />

      <div className="dashboard-main">
        <div className={`list-pane${mobileShowDetail && selectedId ? ' hide-on-mobile' : ''}`}>
          <CaseList
            cases={cases}
            loading={casesLoading}
            error={casesError}
            selectedId={selectedId}
            onSelect={handleSelectCase}
            statusFilter={statusFilter}
            onStatusFilterChange={handleFilterChange}
            typeFilter={typeFilter}
            onTypeFilterChange={handleTypeFilterChange}
          />
        </div>

        <div
          className={`main-panel${selectedId && mobileShowDetail ? ' show-on-mobile' : ''}${!selectedId ? ' empty' : ''}`}
          ref={detailPanelRef}
        >
          {!selectedId ? (
            <div className="no-selection">
              <div className="no-selection-title">Select a customer</div>
              <div className="no-selection-desc">
                Choose a case on the left to see why payment failed, the customer&apos;s
                history, and what RecoverAI recommends next.
              </div>
            </div>
          ) : (
            <CaseDetail
              caseData={caseDetail}
              loading={caseDetailLoading}
              error={caseDetailError}
              customerHistory={customerHistory}
              historyLoading={customerHistoryLoading}
              historyError={customerHistoryError}
              caseStatus={caseDetail?.status}
              agentResult={agentResult}
              agentRunning={agentRunning}
              agentError={agentError}
              onRunAgent={handleRunAgent}
              audit={audit}
              auditLoading={auditLoading}
              auditError={auditError}
              onBack={() => setMobileShowDetail(false)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
