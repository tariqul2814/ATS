import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { History } from './history';
import { AnalysesApiService } from '../../services/analyses-api.service';
import { AnalysisStoreService } from '../../services/analysis-store.service';
import { AnalysisHistoryItem } from '../../models/analysis';

describe('History', () => {
  let api: jasmine.SpyObj<AnalysesApiService>;
  let store: AnalysisStoreService;

  function create() {
    TestBed.configureTestingModule({
      imports: [History],
      providers: [provideRouter([]), { provide: AnalysesApiService, useValue: api }],
    });
    store = TestBed.inject(AnalysisStoreService);
    return store;
  }

  beforeEach(() => {
    api = jasmine.createSpyObj<AnalysesApiService>('AnalysesApiService', ['getHistory']);
    localStorage.clear();
  });

  afterEach(() => localStorage.clear());

  it('merges API status with local metadata, newest first, and flags unavailable ids', () => {
    create();
    store.add({ analysisId: 'a', fileName: 'a.pdf', createdAt: '2026-01-01T00:00:00Z' });
    store.add({ analysisId: 'b', fileName: 'b.pdf', createdAt: '2026-01-02T00:00:00Z' });

    const items: AnalysisHistoryItem[] = [
      { analysisId: 'a', status: 'Completed', createdAt: '2026-01-01T00:00:00Z', hasResult: true },
      // 'b' omitted by the backend
    ];
    api.getHistory.and.returnValue(of(items));

    const c = TestBed.createComponent(History).componentInstance;
    c.ngOnInit();

    const rows = c.rows();
    expect(rows.map((r) => r.analysisId)).toEqual(['b', 'a']); // newest first
    expect(rows[0].status).toBe('Unavailable');
    expect(rows[0].available).toBeFalse();
    expect(rows[1].status).toBe('Completed');
    expect(rows[1].hasResult).toBeTrue();
  });

  it('shows the empty state with no retained ids and does not call the API', () => {
    create();
    const c = TestBed.createComponent(History).componentInstance;
    c.ngOnInit();
    expect(c.empty()).toBeTrue();
    expect(api.getHistory).not.toHaveBeenCalled();
  });
});
