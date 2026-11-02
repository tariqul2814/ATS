import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';

import { Submit } from './submit';
import { AnalysesApiService } from '../../services/analyses-api.service';
import { AnalysisStoreService } from '../../services/analysis-store.service';

function fileEvent(file: File | null): Event {
  return { target: { files: file ? [file] : [] } } as unknown as Event;
}

const pdf = () => new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' });

describe('Submit', () => {
  let api: jasmine.SpyObj<AnalysesApiService>;
  let router: jasmine.SpyObj<Router>;
  let store: AnalysisStoreService;

  beforeEach(() => {
    api = jasmine.createSpyObj<AnalysesApiService>('AnalysesApiService', ['submit']);
    router = jasmine.createSpyObj<Router>('Router', ['navigate']);
    localStorage.clear();

    TestBed.configureTestingModule({
      imports: [Submit],
      providers: [
        { provide: AnalysesApiService, useValue: api },
        { provide: Router, useValue: router },
      ],
    });
    store = TestBed.inject(AnalysisStoreService);
  });

  afterEach(() => localStorage.clear());

  it('is not submittable until a valid file and job description are present', () => {
    const c = TestBed.createComponent(Submit).componentInstance;
    expect(c.canSubmit).toBeFalse();

    c.jobDescription.setValue('a role');
    c.onFileSelected(fileEvent(pdf()));
    expect(c.canSubmit).toBeTrue();
  });

  it('rejects a disallowed file type', () => {
    const c = TestBed.createComponent(Submit).componentInstance;
    c.onFileSelected(fileEvent(new File(['x'], 'cv.txt', { type: 'text/plain' })));
    expect(c.file()).toBeNull();
    expect(c.fileError()).toContain('.pdf');
  });

  it('rejects an oversized file', () => {
    const c = TestBed.createComponent(Submit).componentInstance;
    const big = new File([new Uint8Array(6 * 1024 * 1024)], 'big.pdf', { type: 'application/pdf' });
    c.onFileSelected(fileEvent(big));
    expect(c.file()).toBeNull();
    expect(c.fileError()).toContain('too large');
  });

  it('on 202 stores the id and navigates to the detail view', () => {
    api.submit.and.returnValue(of({ analysisId: 'the-id', status: 'Pending' as const }));
    const c = TestBed.createComponent(Submit).componentInstance;

    c.jobDescription.setValue('a role');
    c.onFileSelected(fileEvent(pdf()));
    c.submit();

    expect(api.submit).toHaveBeenCalled();
    expect(store.ids()).toContain('the-id');
    expect(router.navigate).toHaveBeenCalledWith(['/analyses', 'the-id']);
  });

  it('shows the backend message on a 400 rejection', () => {
    api.submit.and.returnValue(
      throwError(() => new HttpErrorResponse({ status: 400, error: { error: 'Bad file.' } })),
    );
    const c = TestBed.createComponent(Submit).componentInstance;

    c.jobDescription.setValue('a role');
    c.onFileSelected(fileEvent(pdf()));
    c.submit();

    expect(c.submitError()).toBe('Bad file.');
    expect(c.submitting()).toBeFalse();
    expect(router.navigate).not.toHaveBeenCalled();
  });
});
