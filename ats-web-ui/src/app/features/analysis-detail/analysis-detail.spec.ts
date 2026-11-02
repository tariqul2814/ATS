import { TestBed, fakeAsync, tick, discardPeriodicTasks } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';

import { AnalysisDetail } from './analysis-detail';
import { AnalysesApiService } from '../../services/analyses-api.service';
import { AnalysisHubService } from '../../services/analysis-hub.service';
import { AnalysisStatusDto, AnalysisStatus } from '../../models/analysis';
import { sampleResult } from '../../testing/analysis-result.fixture';

const dto = (status: AnalysisStatus, over: Partial<AnalysisStatusDto> = {}): AnalysisStatusDto => ({
  analysisId: 'the-id',
  status,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  resultJson: null,
  error: null,
  ...over,
});

class FakeHub {
  readonly updates$ = new Subject<AnalysisStatusDto>();
  readonly updates = this.updates$.asObservable();
  startResult: Promise<void> = Promise.resolve();
  start = jasmine.createSpy('start').and.callFake(() => this.startResult);
  stop = jasmine.createSpy('stop').and.returnValue(Promise.resolve());
}

describe('AnalysisDetail', () => {
  let api: jasmine.SpyObj<AnalysesApiService>;
  let hub: FakeHub;

  function setup() {
    TestBed.configureTestingModule({
      imports: [AnalysisDetail],
      providers: [
        provideRouter([]),
        { provide: AnalysesApiService, useValue: api },
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: 'the-id' }) } } },
      ],
    });
    TestBed.overrideComponent(AnalysisDetail, {
      set: { providers: [{ provide: AnalysisHubService, useValue: hub }] },
    });
    return TestBed.createComponent(AnalysisDetail);
  }

  beforeEach(() => {
    api = jasmine.createSpyObj<AnalysesApiService>('AnalysesApiService', ['getStatus']);
    hub = new FakeHub();
  });

  it('seeds the status from the API on open', () => {
    api.getStatus.and.returnValue(of(dto('Pending')));
    const c = setup().componentInstance;
    c.ngOnInit();
    expect(c.status()?.status).toBe('Pending');
    expect(c.loading()).toBeFalse();
  });

  it('renders a terminal analysis without connecting the hub', fakeAsync(() => {
    api.getStatus.and.returnValue(of(dto('Completed', { resultJson: '{"score":80}' })));
    const c = setup().componentInstance;
    c.ngOnInit();
    tick();
    expect(c.isTerminal()).toBeTrue();
    expect(c.formattedResult()).toContain('"score": 80');
    expect(hub.start).not.toHaveBeenCalled();
  }));

  it('applies a live analysisUpdated push', fakeAsync(() => {
    api.getStatus.and.returnValue(of(dto('Dispatched')));
    const c = setup().componentInstance;
    c.ngOnInit();
    tick(); // resolve hub.start()
    expect(hub.start).toHaveBeenCalled();

    hub.updates$.next(dto('Completed', { resultJson: '{"ok":true}' }));
    expect(c.state()).toBe('Completed');
    expect(hub.stop).toHaveBeenCalled(); // terminal → tears down
  }));

  it('shows not-found on a 404 seed', () => {
    api.getStatus.and.returnValue(throwError(() => new HttpErrorResponse({ status: 404 })));
    const c = setup().componentInstance;
    c.ngOnInit();
    expect(c.notFound()).toBeTrue();
  });

  it('falls back to polling when the hub fails to start', fakeAsync(() => {
    api.getStatus.and.returnValue(of(dto('Dispatched')));
    hub.startResult = Promise.reject(new Error('no socket'));
    const c = setup().componentInstance;
    c.ngOnInit();
    tick(); // reject hub.start() → startPolling
    expect(c.live()).toBeFalse();

    const callsAfterSeed = api.getStatus.calls.count();
    tick(5000);
    expect(api.getStatus.calls.count()).toBeGreaterThan(callsAfterSeed);
    discardPeriodicTasks();
  }));

  it('renders a scoring-engine result with the results view', fakeAsync(() => {
    api.getStatus.and.returnValue(of(dto('Completed', { resultJson: JSON.stringify(sampleResult()) })));
    const f = setup();
    f.componentInstance.ngOnInit();
    tick();
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('app-result-view')).not.toBeNull();
    expect(el.querySelector('.ring-value')?.textContent?.trim()).toBe('72');
    // Raw JSON stays available, collapsed.
    expect(el.querySelector('details.raw pre.result')?.textContent).toContain('"score": 72');
    expect(el.querySelector('details.raw')?.hasAttribute('open')).toBeFalse();
  }));

  it('falls back to formatted JSON for a result of unknown shape', fakeAsync(() => {
    api.getStatus.and.returnValue(of(dto('Completed', { resultJson: '{"score":80}' })));
    const f = setup();
    f.componentInstance.ngOnInit();
    tick();
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('app-result-view')).toBeNull();
    expect(el.querySelector('pre.result')?.textContent).toContain('"score": 80');
  }));

  it('downloads the markdown report', fakeAsync(() => {
    api.getStatus.and.returnValue(of(dto('Completed', { resultJson: JSON.stringify(sampleResult()) })));
    const c = setup().componentInstance;
    c.ngOnInit();
    tick();
    const createUrl = spyOn(URL, 'createObjectURL').and.returnValue('blob:report');
    spyOn(URL, 'revokeObjectURL');
    const click = spyOn(HTMLAnchorElement.prototype, 'click');

    c.downloadReport();

    const blob = createUrl.calls.mostRecent().args[0] as Blob;
    expect(blob.type).toBe('text/markdown');
    expect(blob.size).toBe(new TextEncoder().encode(sampleResult().reportMarkdown).length);
    expect(click).toHaveBeenCalled();
  }));

  it('tears down on destroy', () => {
    api.getStatus.and.returnValue(of(dto('Dispatched')));
    const c = setup().componentInstance;
    c.ngOnInit();
    c.ngOnDestroy();
    expect(hub.stop).toHaveBeenCalled();
  });
});
