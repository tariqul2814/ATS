import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';

import { AnalysesApiService } from './analyses-api.service';
import { environment } from '../../environments/environment';
import { AnalysisAccepted } from '../models/analysis';

describe('AnalysesApiService', () => {
  let service: AnalysesApiService;
  let httpMock: HttpTestingController;
  const base = environment.apiBaseUrl;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [AnalysesApiService, provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AnalysesApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('POSTs multipart form data to /api/analyses', () => {
    const file = new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' });
    const accepted: AnalysisAccepted = { analysisId: 'abc', status: 'Pending' };

    service.submit(file, 'a job description').subscribe((res) => {
      expect(res).toEqual(accepted);
    });

    const req = httpMock.expectOne(`${base}/api/analyses`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body instanceof FormData).toBeTrue();
    const body = req.request.body as FormData;
    expect(body.get('jobDescription')).toBe('a job description');
    expect(body.get('files')).toBeInstanceOf(File);
    req.flush(accepted);
  });

  it('builds the history request with a comma-joined ids param', () => {
    service.getHistory(['g1', 'g2']).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${base}/api/analyses`);
    expect(req.request.params.get('ids')).toBe('g1,g2');
    req.flush([]);
  });

  it('requests the result endpoint as text', () => {
    service.getResult('abc').subscribe();
    const req = httpMock.expectOne(`${base}/api/analyses/abc/result`);
    expect(req.request.method).toBe('GET');
    expect(req.request.responseType).toBe('text');
    req.flush('{}');
  });
});
