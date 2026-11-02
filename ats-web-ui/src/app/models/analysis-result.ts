/**
 * The analysis result document produced by the Python scoring engine (ats-fastapi `AnalysisResult`)
 * and stored opaquely by the orchestrator as `resultJson`.
 */

export type Band = 'Strong' | 'Good' | 'Moderate' | 'Weak';

export type Category =
  | 'keyword_match'
  | 'experience_relevance'
  | 'achievements_impact'
  | 'ats_formatting'
  | 'education_certifications';

export interface CategoryScore {
  category: Category;
  score: number;
  max: number;
  reason: string;
}

export interface MissingKeyword {
  keyword: string;
  requirement: 'required' | 'preferred';
  /** Where in the CV to mention it; null when the CV shows no basis for the skill. */
  whereToAdd: string | null;
  /** True when the CV shows no basis for the skill (don't suggest adding it). */
  skillGap: boolean;
}

export interface Improvement {
  section: string;
  problem: string;
  original: string;
  suggested: string;
}

export interface AnalysisResult {
  score: number;
  band: Band;
  breakdown: CategoryScore[];
  summary: string;
  matchedKeywords: string[];
  missingKeywords: MissingKeyword[];
  formattingIssues: string[];
  topImprovements: Improvement[];
  strengths: string[];
  revisedSummary: string;
  reportMarkdown: string;
}

export const CATEGORY_LABELS: Record<Category, string> = {
  keyword_match: 'Keyword match',
  experience_relevance: 'Experience relevance',
  achievements_impact: 'Achievements & impact',
  ats_formatting: 'ATS formatting',
  education_certifications: 'Education & certifications',
};

const BANDS: readonly Band[] = ['Strong', 'Good', 'Moderate', 'Weak'];

/**
 * Parses `resultJson` into a typed result when it has the scoring engine's shape. Returns null for
 * anything else (invalid JSON, another schema), so callers can fall back to a generic JSON view
 * instead of failing (frontend Requirement 5.2).
 */
export function parseAnalysisResult(raw: string | null | undefined): AnalysisResult | null {
  if (!raw) return null;
  let doc: unknown;
  try {
    doc = JSON.parse(raw);
  } catch {
    return null;
  }
  return isAnalysisResult(doc) ? doc : null;
}

function isAnalysisResult(value: unknown): value is AnalysisResult {
  if (!isObject(value)) return false;
  return (
    typeof value['score'] === 'number' &&
    BANDS.includes(value['band'] as Band) &&
    isArrayOf(value['breakdown'], isCategoryScore) &&
    typeof value['summary'] === 'string' &&
    isArrayOf(value['matchedKeywords'], isString) &&
    isArrayOf(value['missingKeywords'], isMissingKeyword) &&
    isArrayOf(value['formattingIssues'], isString) &&
    isArrayOf(value['topImprovements'], isImprovement) &&
    isArrayOf(value['strengths'], isString) &&
    typeof value['revisedSummary'] === 'string' &&
    typeof value['reportMarkdown'] === 'string'
  );
}

function isCategoryScore(v: unknown): v is CategoryScore {
  return (
    isObject(v) &&
    typeof v['category'] === 'string' &&
    v['category'] in CATEGORY_LABELS &&
    typeof v['score'] === 'number' &&
    typeof v['max'] === 'number' &&
    typeof v['reason'] === 'string'
  );
}

function isMissingKeyword(v: unknown): v is MissingKeyword {
  return (
    isObject(v) &&
    typeof v['keyword'] === 'string' &&
    (v['requirement'] === 'required' || v['requirement'] === 'preferred') &&
    (v['whereToAdd'] === null || typeof v['whereToAdd'] === 'string') &&
    typeof v['skillGap'] === 'boolean'
  );
}

function isImprovement(v: unknown): v is Improvement {
  return (
    isObject(v) &&
    ['section', 'problem', 'original', 'suggested'].every((k) => typeof v[k] === 'string')
  );
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function isString(v: unknown): v is string {
  return typeof v === 'string';
}

function isArrayOf<T>(v: unknown, check: (item: unknown) => item is T): v is T[] {
  return Array.isArray(v) && v.every(check);
}
