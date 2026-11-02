import { AnalysisResult } from '../models/analysis-result';

/** A result in the exact shape the ats-fastapi scoring engine sends (test data only). */
export function sampleResult(over: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    score: 72,
    band: 'Good',
    breakdown: [
      { category: 'keyword_match', score: 26, max: 35, reason: 'Python and FastAPI present; Kubernetes absent.' },
      { category: 'experience_relevance', score: 19, max: 25, reason: 'Four years of backend API work.' },
      { category: 'achievements_impact', score: 10, max: 15, reason: 'Two quantified results.' },
      { category: 'ats_formatting', score: 11, max: 15, reason: 'Standard headings.' },
      { category: 'education_certifications', score: 6, max: 10, reason: 'Relevant degree.' },
    ],
    summary: 'Solid backend match held back by missing infrastructure keywords.',
    matchedKeywords: ['Python', 'FastAPI', 'PostgreSQL'],
    missingKeywords: [
      { keyword: 'Kubernetes', requirement: 'required', whereToAdd: null, skillGap: true },
      { keyword: 'CI/CD', requirement: 'preferred', whereToAdd: 'Experience > Acme Corp', skillGap: false },
    ],
    formattingIssues: ['Skills are embedded in the summary.'],
    topImprovements: [
      {
        section: 'Experience',
        problem: 'Duty-only bullet.',
        original: 'Worked on the payments API.',
        suggested: 'Built payments API endpoints serving 2M requests/day.',
      },
    ],
    strengths: ['Relevant Python API experience'],
    revisedSummary: 'Backend engineer with four years building Python REST APIs.',
    reportMarkdown: '# ATS assessment\n\n**Score:** 72/100 — **Good**\n',
    ...over,
  };
}
