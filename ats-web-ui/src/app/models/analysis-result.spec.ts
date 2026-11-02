import { parseAnalysisResult } from './analysis-result';
import { sampleResult } from '../testing/analysis-result.fixture';

describe('parseAnalysisResult', () => {
  it('parses a scoring-engine result', () => {
    const parsed = parseAnalysisResult(JSON.stringify(sampleResult()));
    expect(parsed?.score).toBe(72);
    expect(parsed?.breakdown.length).toBe(5);
    expect(parsed?.missingKeywords[0].skillGap).toBeTrue();
  });

  it('keeps non-ASCII text intact', () => {
    const parsed = parseAnalysisResult(JSON.stringify(sampleResult({ summary: 'Développeur — 5 ans' })));
    expect(parsed?.summary).toBe('Développeur — 5 ans');
  });

  it('returns null for empty or invalid JSON', () => {
    expect(parseAnalysisResult(null)).toBeNull();
    expect(parseAnalysisResult('')).toBeNull();
    expect(parseAnalysisResult('{not json')).toBeNull();
  });

  it('returns null for a document of another shape', () => {
    expect(parseAnalysisResult('{"score":80}')).toBeNull();
    expect(parseAnalysisResult('[1,2,3]')).toBeNull();
  });

  it('returns null when a field has the wrong type or value', () => {
    const cases = [
      { band: 'Excellent' },
      { score: '72' },
      { breakdown: [{ category: 'unknown', score: 1, max: 2, reason: '' }] },
      { missingKeywords: [{ keyword: 'Go', requirement: 'nice', whereToAdd: null, skillGap: true }] },
      { topImprovements: [{ section: 'X', problem: 'Y' }] },
      { matchedKeywords: [1, 2] },
    ];
    for (const over of cases) {
      const doc = { ...sampleResult(), ...over };
      expect(parseAnalysisResult(JSON.stringify(doc)))
        .withContext(JSON.stringify(over))
        .toBeNull();
    }
  });

  it('returns null when a required field is missing', () => {
    const { reportMarkdown, ...rest } = sampleResult();
    expect(reportMarkdown).toBeTruthy();
    expect(parseAnalysisResult(JSON.stringify(rest))).toBeNull();
  });
});
