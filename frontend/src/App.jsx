/**
 * RecoverAI Dashboard
 * All data from FastAPI backend. No hardcoded values.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import './index.css';

import {
  getHealth, getDashboardSummary, getRecoveryCases,
  getRecoveryCase, getRecoveryAudit, runRecoveryAgent, getCustomerHistory,
} from './services/api.js';

import SummaryCards from './components/SummaryCards.jsx';
import CaseList     from './components/CaseList.jsx';
import CaseDetail   from './components/CaseDetail.jsx';

/* 4-pointed star logo matching reference image */
function StarLogo() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
      <path d="M14 2 L16.5 11.5 L26 14 L16.5 16.5 L14 26 L11.5 16.5 L2 14 L11.5 11.5 Z"
        fill="#7c3aed" stroke="#7c3aed" strokeWidth="0.5" strokeLinejoin="round"/>
    </svg>
  );
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center p-12 bg-[#f8f9fb]">
      <div className="w-16 h-16 rounded-2xl bg-white border border-gray-200 flex items-center justify-center shadow-sm mb-2">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="1.5" strokeLinecap="round">
          <path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"/>
        </svg>
      </div>
      <p className="text-lg font-bold text-gray-800">Select a recovery case</p>
      <p className="text-sm text-gray-400 max-w-[240px] leading-relaxed">
        Choose a customer from the left to review their case and take action.
      </p>
    </div>
  );
}

export default function App() {
  const [backendOnline, setBackendOnline]         = useState(null);
  const [summary, setSummary]                     = useState(null);
  const [summaryLoading, setSummaryLoading]       = useState(true);
  const [summaryError, setSummaryError]           = useState(null);
  const [cases, setCases]                         = useState([]);
  const [casesLoading, setCasesLoading]           = useState(true);
  const [casesError, setCasesError]               = useState(null);
  const [statusFilter, setStatusFilter]           = useState('');
  const [typeFilter, setTypeFilter]               = useState('');
  const [selectedId, setSelectedId]               = useState(null);
  const [caseDetail, setCaseDetail]               = useState(null);
  const [caseDetailLoading, setCaseDetailLoading] = useState(false);
  const [caseDetailError, setCaseDetailError]     = useState(null);
  const [customerHistory, setCustomerHistory]     = useState(null);
  const [customerHistoryLoading, setCustomerHistoryLoading] = useState(false);
  const [customerHistoryError, setCustomerHistoryError]     = useState(null);
  const [audit, setAudit]                         = useState(null);
  const [auditLoading, setAuditLoading]           = useState(false);
  const [auditError, setAuditError]               = useState(null);
  const [agentRunning, setAgentRunning]           = useState(false);
  const [agentResult, setAgentResult]             = useState(null);
  const [agentError, setAgentError]               = useState(null);
  const detailRef = useRef(null);

  useEffect(() => {
    getHealth().then(() => setBackendOnline(true)).catch(() => setBackendOnline(false));
  }, []);

  const loadSummary = useCallback(async () => {
    setSummaryLoading(true); setSummaryError(null);
    try { setSummary(await getDashboardSummary()); }
    catch (e) { setSummaryError(e.message); }
    finally { setSummaryLoading(false); }
  }, []);

  const loadCases = useCallback(async (status = '', type = '') => {
    setCasesLoading(true); setCasesError(null);
    try {
      const data = await getRecoveryCases({ status: status || undefined, type: type || undefined, limit: 100 });
      setCases(data.cases ?? []);
    }
    catch (e) { setCasesError(e.message); }
    finally { setCasesLoading(false); }
  }, []);

  const loadCaseDetail = useCallback(async (id) => {
    setCaseDetailLoading(true); setCaseDetailError(null); setCaseDetail(null);
    try { setCaseDetail(await getRecoveryCase(id)); }
    catch (e) { setCaseDetailError(e.message); }
    finally { setCaseDetailLoading(false); }
  }, []);

  const loadCustomerHistory = useCallback(async (id) => {
    setCustomerHistoryLoading(true); setCustomerHistoryError(null); setCustomerHistory(null);
    try { setCustomerHistory(await getCustomerHistory(id)); }
    catch (e) { setCustomerHistoryError(e.message); }
    finally { setCustomerHistoryLoading(false); }
  }, []);

  const loadAudit = useCallback(async (id) => {
    setAuditLoading(true); setAuditError(null);
    try { setAudit(await getRecoveryAudit(id)); }
    catch (e) { setAuditError(e.message); }
    finally { setAuditLoading(false); }
  }, []);

  useEffect(() => {
    loadSummary();
    loadCases(statusFilter, typeFilter);
  }, []); // eslint-disable-line

  const handleFilterChange = v => { setStatusFilter(v); loadCases(v, typeFilter); };
  const handleTypeChange   = v => { setTypeFilter(v);   loadCases(statusFilter, v); };

  const handleSelectCase = (id) => {
    setSelectedId(id);
    setCaseDetail(null); setAgentResult(null); setAgentError(null);
    setAudit(null); setCustomerHistory(null);
    loadCaseDetail(id); loadAudit(id); loadCustomerHistory(id);
  };

  useEffect(() => {
    if (detailRef.current) detailRef.current.scrollTop = 0;
  }, [selectedId]);

  const handleRunAgent = async () => {
    if (!selectedId || agentRunning) return;
    setAgentRunning(true); setAgentResult(null); setAgentError(null);
    try {
      const result = await runRecoveryAgent(selectedId);
      setAgentResult(result);
      await Promise.all([
        loadSummary(), loadCases(statusFilter, typeFilter),
        loadCaseDetail(selectedId), loadAudit(selectedId), loadCustomerHistory(selectedId),
      ]);
    }
    catch (e) { setAgentError(e.message); }
    finally { setAgentRunning(false); }
  };

  return (
    <div className="h-screen max-h-screen overflow-hidden flex flex-col bg-[#f8f9fb] font-sans text-sm text-gray-700">

      {/* ─── Header ─────────────────────────────────────── */}
      <header className="h-14 bg-white border-b border-gray-100 px-6 flex items-center justify-between flex-shrink-0 z-50">
        <div className="flex items-center gap-2.5">
          <StarLogo />
          <div>
            <span className="text-[22px] font-black text-gray-900 tracking-tight">RecoverAI</span>
            <p className="text-[11px] font-medium text-gray-500 leading-none mt-0.5">AI-Powered Revenue Recovery</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {backendOnline === null && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border border-gray-200 bg-gray-50 text-gray-500">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-pulse" /> Connecting
            </span>
          )}
          {backendOnline === true && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border border-green-200 bg-green-50 text-green-700">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" /> Live
            </span>
          )}
          {backendOnline === false && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border border-red-200 bg-red-50 text-red-600">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" /> Offline
            </span>
          )}
        </div>
      </header>

      {backendOnline === false && (
        <div className="mx-6 mt-2 px-4 py-2.5 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600 font-medium flex-shrink-0">
          Backend unavailable. Start the server on port 8000 and refresh.
        </div>
      )}

      {/* ─── Summary cards ──────────────────────────────── */}
      <SummaryCards summary={summary} loading={summaryLoading} error={summaryError} />

      {/* ─── Master / detail ────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-hidden flex">
        {/* Left: case list — always visible */}
        <div className="w-[300px] flex-shrink-0 min-h-0 flex flex-col border-r border-gray-200 bg-white">
          <CaseList
            cases={cases} loading={casesLoading} error={casesError}
            selectedId={selectedId} onSelect={handleSelectCase}
            statusFilter={statusFilter} onStatusFilterChange={handleFilterChange}
            typeFilter={typeFilter} onTypeFilterChange={handleTypeChange}
          />
        </div>

        {/* Right: detail */}
        <div ref={detailRef} className="flex-1 min-h-0 overflow-y-auto scrollbar-thin bg-[#f8f9fb]">
          {!selectedId
            ? <EmptyState />
            : <CaseDetail
                caseData={caseDetail} loading={caseDetailLoading} error={caseDetailError}
                customerHistory={customerHistory} historyLoading={customerHistoryLoading} historyError={customerHistoryError}
                caseStatus={caseDetail?.status}
                agentResult={agentResult} agentRunning={agentRunning} agentError={agentError}
                onRunAgent={handleRunAgent}
                audit={audit} auditLoading={auditLoading} auditError={auditError}
              />
          }
        </div>
      </div>
    </div>
  );
}
