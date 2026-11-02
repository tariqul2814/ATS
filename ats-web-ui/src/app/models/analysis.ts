/**
 * Client-side models mirroring the .NET orchestrator's DTOs (see ats-backend spec).
 * Field names match the JSON the API emits (camelCased by ASP.NET's web defaults).
 */

/** The four lifecycle states (backend AnalysisStatus). */
export type AnalysisStatus = 'Pending' | 'Dispatched' | 'Completed' | 'Failed';

/** Terminal states — no further transitions occur. */
export const TERMINAL_STATUSES: readonly AnalysisStatus[] = ['Completed', 'Failed'];

export function isTerminal(status: AnalysisStatus | null | undefined): boolean {
  return status != null && TERMINAL_STATUSES.includes(status);
}

/** 202 response body from POST /api/analyses (backend AnalysisAccepted). */
export interface AnalysisAccepted {
  analysisId: string;
  status: AnalysisStatus;
}

/**
 * GET /api/analyses/{id} and the SignalR `analysisUpdated` payload (backend AnalysisStatusDto).
 * `resultJson` is the raw analysis document as a JSON string (present when Completed);
 * `error` is the failure reason (present when Failed).
 */
export interface AnalysisStatusDto {
  analysisId: string;
  status: AnalysisStatus;
  createdAt: string; // ISO-8601
  updatedAt: string; // ISO-8601
  resultJson: string | null;
  error: string | null;
}

/** GET /api/analyses?ids=... item (backend AnalysisHistoryItem). */
export interface AnalysisHistoryItem {
  analysisId: string;
  status: AnalysisStatus;
  createdAt: string; // ISO-8601
  hasResult: boolean;
}

/**
 * Locally retained record of an analysis this browser created. The GUID is the only
 * server-side handle; the rest is convenience metadata kept client-side (Requirement 6).
 */
export interface StoredAnalysis {
  analysisId: string;
  fileName: string;
  createdAt: string; // ISO-8601, client clock
}
