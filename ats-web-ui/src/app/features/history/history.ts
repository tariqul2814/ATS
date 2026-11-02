import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';

import { AnalysesApiService } from '../../services/analyses-api.service';
import { AnalysisStoreService } from '../../services/analysis-store.service';
import { AnalysisHistoryItem, StoredAnalysis } from '../../models/analysis';

interface HistoryRow {
  analysisId: string;
  fileName: string;
  createdAt: string;
  status: string; // API status, or 'Unavailable' when the backend didn't return it
  hasResult: boolean;
  available: boolean;
}

@Component({
  selector: 'app-history',
  imports: [RouterLink, DatePipe],
  templateUrl: './history.html',
  styleUrl: './history.scss',
})
export class History implements OnInit {
  private readonly api = inject(AnalysesApiService);
  private readonly store = inject(AnalysisStoreService);

  readonly loading = signal(true);
  readonly rows = signal<HistoryRow[]>([]);
  readonly empty = computed(() => !this.loading() && this.rows().length === 0);

  ngOnInit(): void {
    const stored = this.store.analyses();
    if (stored.length === 0) {
      this.loading.set(false);
      return;
    }

    this.api.getHistory(stored.map((s) => s.analysisId)).subscribe({
      next: (items) => {
        this.rows.set(this.merge(stored, items));
        this.loading.set(false);
      },
      error: () => {
        // Even if the call fails, show what we retained locally (Requirement 7.4).
        this.rows.set(this.merge(stored, []));
        this.loading.set(false);
      },
    });
  }

  remove(analysisId: string, event: Event): void {
    event.stopPropagation();
    this.store.remove(analysisId);
    this.rows.set(this.rows().filter((r) => r.analysisId !== analysisId));
  }

  /** Join locally retained metadata with the API's authoritative status, newest first. */
  private merge(stored: StoredAnalysis[], items: AnalysisHistoryItem[]): HistoryRow[] {
    const byId = new Map(items.map((i) => [i.analysisId, i]));
    return stored
      .map<HistoryRow>((s) => {
        const item = byId.get(s.analysisId);
        return {
          analysisId: s.analysisId,
          fileName: s.fileName,
          createdAt: s.createdAt,
          status: item?.status ?? 'Unavailable',
          hasResult: item?.hasResult ?? false,
          available: item !== undefined,
        };
      })
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }
}
