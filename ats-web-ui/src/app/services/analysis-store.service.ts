import { Injectable, signal } from '@angular/core';

import { StoredAnalysis } from '../models/analysis';

const STORAGE_KEY = 'ats.analyses.v1';

/**
 * Browser-local record of the analyses this device created (Requirement 6). Because the backend
 * has no list-all endpoint, these retained GUIDs are the sole "my analyses" list. Every storage
 * access is guarded so a disabled/cleared/unavailable store degrades gracefully (Requirement 6.3).
 */
@Injectable({ providedIn: 'root' })
export class AnalysisStoreService {
  /** Reactive view of the stored analyses, newest first. */
  readonly analyses = signal<StoredAnalysis[]>(this.read());

  /** Record a newly created analysis (idempotent on id). */
  add(entry: StoredAnalysis): void {
    const next = [entry, ...this.read().filter((a) => a.analysisId !== entry.analysisId)];
    this.write(next);
  }

  /** Forget an analysis locally (does not delete server-side data — Requirement 6.4). */
  remove(analysisId: string): void {
    this.write(this.read().filter((a) => a.analysisId !== analysisId));
  }

  /** The retained ids, newest first. */
  ids(): string[] {
    return this.read().map((a) => a.analysisId);
  }

  private read(): StoredAnalysis[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw) as unknown;
      if (!Array.isArray(parsed)) return [];
      return parsed.filter(
        (x): x is StoredAnalysis => !!x && typeof (x as StoredAnalysis).analysisId === 'string',
      );
    } catch {
      // Private mode, blocked storage, or corrupt data — behave as if empty.
      return [];
    }
  }

  private write(list: StoredAnalysis[]): void {
    this.analyses.set(list);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    } catch {
      // Storage unavailable/full — keep the in-memory signal so the session still works.
    }
  }
}
