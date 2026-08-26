/**
 * frontend/src/services/api.js
 *
 * Single API service layer for RecoverAI dashboard.
 *
 * All backend calls go through this module.
 * The base URL is read from VITE_API_BASE_URL (set in frontend/.env).
 * Falls back to http://localhost:8000 for local development.
 *
 * SECURITY: Never put GEMINI_API_KEY or DATABASE_URL in VITE_ variables.
 * This file only communicates with the FastAPI backend.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/**
 * Core fetch wrapper — adds JSON headers and consistent error handling.
 * @param {string} path
 * @param {RequestInit} options
 * @returns {Promise<any>}
 */
async function apiFetch(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // response was not JSON
    }
    throw new Error(detail);
  }

  return res.json();
}

// ── Health ────────────────────────────────────────────────────────────────────

/** Check that the backend is reachable. Returns { status: "ok" } */
export async function getHealth() {
  return apiFetch('/health');
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

/**
 * GET /api/dashboard/summary
 * Returns merchant-level metrics for summary cards.
 */
export async function getDashboardSummary() {
  return apiFetch('/api/dashboard/summary');
}

// ── Recovery cases ────────────────────────────────────────────────────────────

/**
 * GET /api/recovery-cases
 * @param {{ status?: string, type?: string, limit?: number, offset?: number }} params
 */
export async function getRecoveryCases(params = {}) {
  const qs = new URLSearchParams();
  if (params.status)  qs.set('status', params.status);
  if (params.type)    qs.set('type',   params.type);
  if (params.limit)   qs.set('limit',  params.limit);
  if (params.offset)  qs.set('offset', params.offset);
  const query = qs.toString() ? `?${qs}` : '';
  return apiFetch(`/api/recovery-cases${query}`);
}

/**
 * GET /api/recovery-cases/{case_id}
 * Returns full case detail including customer, order, payment.
 */
export async function getRecoveryCase(caseId) {
  return apiFetch(`/api/recovery-cases/${caseId}`);
}

/**
 * GET /api/recovery-cases/{case_id}/customer-history
 * Returns aggregated customer history.
 */
export async function getCustomerHistory(caseId) {
  return apiFetch(`/api/recovery-cases/${caseId}/customer-history`);
}

// ── Audit trail ───────────────────────────────────────────────────────────────

/**
 * GET /api/recovery-cases/{case_id}/audit
 * Returns chronological audit log for a case.
 */
export async function getRecoveryAudit(caseId) {
  return apiFetch(`/api/recovery-cases/${caseId}/audit`);
}

// ── Agent ─────────────────────────────────────────────────────────────────────

/**
 * POST /api/recovery-cases/{case_id}/run-agent
 * Triggers the LangGraph + Gemini recovery agent.
 * Returns AgentRunResponse.
 */
export async function runRecoveryAgent(caseId) {
  return apiFetch(`/api/recovery-cases/${caseId}/run-agent`, {
    method: 'POST',
  });
}
