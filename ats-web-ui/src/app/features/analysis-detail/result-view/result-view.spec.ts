import { ComponentFixture, TestBed, fakeAsync, flushMicrotasks, tick } from '@angular/core/testing';

import { ResultView } from './result-view';
import { AnalysisResult } from '../../../models/analysis-result';
import { sampleResult } from '../../../testing/analysis-result.fixture';

describe('ResultView', () => {
  function render(result: AnalysisResult = sampleResult()): ComponentFixture<ResultView> {
    TestBed.configureTestingModule({ imports: [ResultView] });
    const fixture = TestBed.createComponent(ResultView);
    fixture.componentRef.setInput('result', result);
    fixture.detectChanges();
    return fixture;
  }

  const text = (f: ComponentFixture<ResultView>, selector: string) =>
    Array.from((f.nativeElement as HTMLElement).querySelectorAll(selector)).map((e) =>
      (e.textContent ?? '').trim(),
    );

  it('shows the score, band and summary', () => {
    const f = render();
    expect(text(f, '.ring-value')).toEqual(['72']);
    expect(text(f, '.band')).toEqual(['Good match']);
    expect(text(f, '.summary')[0]).toContain('Solid backend match');
    const ring = f.nativeElement.querySelector('.ring') as HTMLElement;
    expect(ring.getAttribute('aria-label')).toBe('ATS score 72 out of 100, Good');
    expect(ring.classList).toContain('band--Good');
  });

  it('renders every breakdown category with a proportional bar', () => {
    const f = render();
    expect(text(f, '.cat-name')).toEqual([
      'Keyword match',
      'Experience relevance',
      'Achievements & impact',
      'ATS formatting',
      'Education & certifications',
    ]);
    expect(text(f, '.cat-score')[0]).toBe('26 / 35');
    const fills = f.nativeElement.querySelectorAll('.bar-fill') as NodeListOf<HTMLElement>;
    expect(fills[0].style.width).toBe('74%'); // 26/35
    expect(fills[0].classList).toContain('level--high');
    expect(fills[4].style.width).toBe('60%'); // 6/10
    expect(fills[4].classList).toContain('level--mid');
  });

  it('separates matched, required and preferred keywords', () => {
    const f = render();
    expect(text(f, '.chip--matched')).toEqual(['Python', 'FastAPI', 'PostgreSQL']);
    expect(text(f, '.kw-group h4').map((t) => t.replace(/\s+/g, ' '))).toEqual([
      'Matched 3',
      'Missing — required 1',
      'Missing — preferred 1',
    ]);
    const hints = text(f, '.hint');
    expect(hints[0]).toContain('Skill gap'); // Kubernetes: no basis in the CV
    expect(hints[1]).toBe('Add to: Experience > Acme Corp');
  });

  it('omits empty keyword groups and says when nothing matched', () => {
    const f = render(sampleResult({ matchedKeywords: [], missingKeywords: [] }));
    expect(text(f, '.kw-group h4').length).toBe(1);
    expect(text(f, '.keywords .muted')[0]).toContain('None of the job');
  });

  it('shows improvements as original vs suggested', () => {
    const f = render();
    expect(text(f, '.imp-head')[0]).toBe('Experience — Duty-only bullet.');
    expect(text(f, '.rewrite-text--before')).toEqual(['Worked on the payments API.']);
    expect(text(f, '.rewrite-text--after')).toEqual(['Built payments API endpoints serving 2M requests/day.']);
  });

  it('hides sections that have no content', () => {
    const f = render(sampleResult({ topImprovements: [], strengths: [], formattingIssues: [] }));
    expect(f.nativeElement.querySelector('.improvements')).toBeNull();
    expect(f.nativeElement.querySelector('.two-col')).toBeNull();
  });

  it('renders model text as text, not HTML', () => {
    const f = render(sampleResult({ summary: '<img src=x onerror=alert(1)>' }));
    expect(f.nativeElement.querySelector('.summary img')).toBeNull();
    expect(text(f, '.summary')[0]).toBe('<img src=x onerror=alert(1)>');
  });

  it('copies the revised summary', fakeAsync(() => {
    const writeText = jasmine.createSpy('writeText').and.returnValue(Promise.resolve());
    spyOnProperty(navigator, 'clipboard', 'get').and.returnValue({ writeText } as unknown as Clipboard);
    const f = render();
    (f.nativeElement.querySelector('.summary-head button') as HTMLButtonElement).click();
    flushMicrotasks();
    f.detectChanges();
    expect(writeText).toHaveBeenCalledWith('Backend engineer with four years building Python REST APIs.');
    expect(text(f, '.summary-head button')).toEqual(['Copied']);
    tick(2000);
    f.detectChanges();
    expect(text(f, '.summary-head button')).toEqual(['Copy']);
  }));
});
