import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { LowerCasePipe } from '@angular/common';
import { Subscription } from 'rxjs';

import { AnalysesApiService } from '../../services/analyses-api.service';
import { AnalysisHubService } from '../../services/analysis-hub.service';
import { AnalysisStatusDto, AnalysisStatus, isTerminal } from '../../models/analysis';
import { parseAnalysisResult } from '../../models/analysis-result';
import { ResultView } from './result-view/result-view';

const POLL_INTERVAL_MS = 5000;

@Component({
  selector: 'app-analysis-detail',
  imports: [RouterLink, LowerCasePipe, ResultView],
  templateUrl: './analysis-detail.html',
  styleUrl: './analysis-detail.scss',
  // A fresh hub connection is scoped to this view and torn down with it (Requirement 3.5).
  providers: [AnalysisHubService],
})
export class AnalysisDetail implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(AnalysesApiService);
  private readonly hub = inject(AnalysisHubService);

  private hubSub?: Subscription;
  private pollTimer?: ReturnType<typeof setInterval>;

  readonly analysisId = signal<string>('');
  readonly status = signal<AnalysisStatusDto | null>(null);
  readonly loading = signal(true);
  readonly notFound = signal(false);
  readonly live = signal(false); // true when receiving pushes, false when polling

  readonly isTerminal = computed(() => isTerminal(this.status()?.status));
  readonly state = computed<AnalysisStatus | null>(() => this.status()?.status ?? null);

  /** Pretty-printed result for display (Requirement 5.2). */
  readonly formattedResult = computed(() => {
    const raw = this.status()?.resultJson;
    if (!raw) return null;
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch {
      return raw; // not valid JSON — show as-is rather than fail
    }
  });

  /** The result as the scoring engine's typed document, or null to fall back to raw JSON. */
  readonly structuredResult = computed(() => parseAnalysisResult(this.status()?.resultJson));

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id') ?? '';
    this.analysisId.set(id);

    // Seed from the API first so a reload / deep-link / terminal analysis shows immediately (Req 4.1/4.2).
    this.seedStatus(() => void this.connect(id));
  }

  private seedStatus(then?: () => void): void {
    this.api.getStatus(this.analysisId()).subscribe({
      next: (dto) => {
        this.applyDto(dto);
        this.loading.set(false);
        then?.();
      },
      error: (err: unknown) => {
        this.loading.set(false);
        if (err instanceof HttpErrorResponse && err.status === 404) {
          this.notFound.set(true);
        } else {
          then?.(); // transient — still try live updates
        }
      },
    });
  }

  private async connect(id: string): Promise<void> {
    if (this.isTerminal() || this.notFound()) return; // nothing more to watch
    try {
      this.hubSub = this.hub.updates.subscribe((dto) => this.applyDto(dto));
      await this.hub.start(id, () => this.seedStatus()); // re-reconcile on reconnect (Req 3.6)
      this.live.set(true);
    } catch {
      // SignalR unavailable — fall back to polling the status endpoint (Requirement 4.3).
      this.live.set(false);
      this.startPolling();
    }
  }

  private startPolling(): void {
    if (this.pollTimer || this.isTerminal()) return;
    this.pollTimer = setInterval(() => {
      this.api.getStatus(this.analysisId()).subscribe({
        next: (dto) => this.applyDto(dto),
        error: () => {
          /* leave previous state; interceptor surfaces persistent failures */
        },
      });
    }, POLL_INTERVAL_MS);
  }

  private applyDto(dto: AnalysisStatusDto): void {
    if (dto.analysisId !== this.analysisId()) return;
    this.status.set(dto);
    if (isTerminal(dto.status)) {
      this.stopPolling();
      void this.hub.stop();
      this.live.set(false);
    }
  }

  private stopPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = undefined;
    }
  }

  copyResult(): void {
    const text = this.formattedResult();
    if (text) void navigator.clipboard?.writeText(text);
  }

  downloadResult(): void {
    const text = this.formattedResult();
    if (text) this.save(text, `analysis-${this.analysisId()}.json`, 'application/json');
  }

  downloadReport(): void {
    const report = this.structuredResult()?.reportMarkdown;
    if (report) this.save(report, `ats-report-${this.analysisId()}.md`, 'text/markdown');
  }

  private save(text: string, fileName: string, type: string): void {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(url);
  }

  ngOnDestroy(): void {
    this.stopPolling();
    this.hubSub?.unsubscribe();
    void this.hub.stop();
  }
}
