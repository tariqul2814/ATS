import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { AnalysisAccepted, AnalysisHistoryItem, AnalysisStatusDto } from '../models/analysis';

/**
 * The single gateway to the orchestrator's HTTP API (Requirement 11.1).
 * Components never call HttpClient directly; they depend on this service.
 */
@Injectable({ providedIn: 'root' })
export class AnalysesApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  /** POST /api/analyses — multipart submission; resolves with the 202 body. */
  submit(file: File, jobDescription: string): Observable<AnalysisAccepted> {
    const form = new FormData();
    // Field names must match the backend endpoint: `files` (IFormFileCollection) + `jobDescription`.
    form.append('files', file, file.name);
    form.append('jobDescription', jobDescription);
    return this.http.post<AnalysisAccepted>(`${this.base}/api/analyses`, form);
  }

  /** GET /api/analyses/{id} — current status snapshot (cache-first on the server). */
  getStatus(analysisId: string): Observable<AnalysisStatusDto> {
    return this.http.get<AnalysisStatusDto>(
      `${this.base}/api/analyses/${encodeURIComponent(analysisId)}`,
    );
  }

  /**
   * GET /api/analyses/{id}/result — the full stored JSON document (as text).
   * Returns 409 while the analysis is not yet Completed; callers should treat that as "in progress".
   */
  getResult(analysisId: string): Observable<string> {
    return this.http.get(`${this.base}/api/analyses/${encodeURIComponent(analysisId)}/result`, {
      responseType: 'text',
    });
  }

  /** GET /api/analyses?ids=g1,g2 — history for the specific ids this browser retained. */
  getHistory(ids: readonly string[]): Observable<AnalysisHistoryItem[]> {
    const params = new HttpParams().set('ids', ids.join(','));
    return this.http.get<AnalysisHistoryItem[]>(`${this.base}/api/analyses`, { params });
  }
}
