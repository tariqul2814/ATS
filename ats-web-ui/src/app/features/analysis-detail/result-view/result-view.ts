import { Component, computed, input, signal } from '@angular/core';

import { AnalysisResult, CATEGORY_LABELS, CategoryScore } from '../../../models/analysis-result';

/** Renders a scored analysis: score, breakdown, keywords, improvements and summary. */
@Component({
  selector: 'app-result-view',
  templateUrl: './result-view.html',
  styleUrl: './result-view.scss',
})
export class ResultView {
  readonly result = input.required<AnalysisResult>();

  readonly labels = CATEGORY_LABELS;
  readonly summaryCopied = signal(false);

  /** Missing keywords split by requirement; empty groups are left out. */
  readonly missingGroups = computed(() => {
    const missing = this.result().missingKeywords;
    return [
      { title: 'Missing — required', items: missing.filter((k) => k.requirement === 'required') },
      { title: 'Missing — preferred', items: missing.filter((k) => k.requirement === 'preferred') },
    ].filter((g) => g.items.length > 0);
  });

  percent(item: CategoryScore): number {
    return item.max > 0 ? Math.round((item.score / item.max) * 100) : 0;
  }

  level(item: CategoryScore): 'high' | 'mid' | 'low' {
    const pct = this.percent(item);
    return pct >= 70 ? 'high' : pct >= 45 ? 'mid' : 'low';
  }

  copySummary(): void {
    void navigator.clipboard?.writeText(this.result().revisedSummary).then(() => {
      this.summaryCopied.set(true);
      setTimeout(() => this.summaryCopied.set(false), 2000);
    });
  }
}
