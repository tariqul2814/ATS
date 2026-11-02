import { TestBed } from '@angular/core/testing';

import { AnalysisStoreService } from './analysis-store.service';
import { StoredAnalysis } from '../models/analysis';

const entry = (id: string, createdAt: string): StoredAnalysis => ({
  analysisId: id,
  fileName: `${id}.pdf`,
  createdAt,
});

describe('AnalysisStoreService', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({});
  });

  afterEach(() => localStorage.clear());

  it('adds entries newest-first and dedupes by id', () => {
    const svc = TestBed.inject(AnalysisStoreService);
    svc.add(entry('a', '2026-01-01T00:00:00Z'));
    svc.add(entry('b', '2026-01-02T00:00:00Z'));
    svc.add(entry('a', '2026-01-03T00:00:00Z')); // re-add a

    expect(svc.ids()).toEqual(['a', 'b']);
    expect(svc.analyses()[0].analysisId).toBe('a');
    expect(svc.analyses().length).toBe(2);
  });

  it('removes an entry locally', () => {
    const svc = TestBed.inject(AnalysisStoreService);
    svc.add(entry('a', '2026-01-01T00:00:00Z'));
    svc.add(entry('b', '2026-01-02T00:00:00Z'));
    svc.remove('a');
    expect(svc.ids()).toEqual(['b']);
  });

  it('degrades gracefully when localStorage throws', () => {
    const getSpy = spyOn(Storage.prototype, 'getItem').and.throwError('blocked');
    const setSpy = spyOn(Storage.prototype, 'setItem').and.throwError('blocked');

    const svc = TestBed.inject(AnalysisStoreService);
    expect(svc.analyses()).toEqual([]); // read swallowed → empty
    expect(() => svc.add(entry('a', '2026-01-01T00:00:00Z'))).not.toThrow(); // write swallowed
    expect(svc.analyses()[0].analysisId).toBe('a'); // in-memory signal still updated

    getSpy.and.callThrough();
    setSpy.and.callThrough();
  });
});
