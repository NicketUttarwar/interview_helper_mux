import type { TranscriptWord } from "../types";

export const FUZZY_MATCH_FLOOR = 80;
export const FUZZY_MATCH_DEFAULT = 90;

export interface FuzzyMatch {
  index: number;
  text: string;
  score: number;
  start_ms: number;
}

/** Lowercase and strip leading/trailing punctuation for comparison. */
export function normalizeWordToken(text: string): string {
  return text.toLowerCase().replace(/^[^\w]+|[^\w]+$/g, "");
}

export function correctionDiffersFromSource(source: string, correction: string): boolean {
  const a = normalizeWordToken(source);
  const b = normalizeWordToken(correction);
  return Boolean(b) && a !== b;
}

function levenshteinDistance(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;

  const prev = new Array<number>(b.length + 1);
  const curr = new Array<number>(b.length + 1);

  for (let j = 0; j <= b.length; j++) prev[j] = j;

  for (let i = 1; i <= a.length; i++) {
    curr[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    for (let j = 0; j <= b.length; j++) prev[j] = curr[j];
  }

  return prev[b.length];
}

/** Normalized Levenshtein similarity as 0–100 integer. */
export function fuzzyWordScore(source: string, target: string): number {
  const a = normalizeWordToken(source);
  const b = normalizeWordToken(target);
  if (!a || !b) return 0;
  if (a === b) return 100;
  const maxLen = Math.max(a.length, b.length);
  const dist = levenshteinDistance(a, b);
  return Math.round((1 - dist / maxLen) * 100);
}

export function clampFuzzyMinScore(score: number): number {
  return Math.min(100, Math.max(FUZZY_MATCH_FLOOR, score));
}

export function findFuzzyWordMatches(
  words: TranscriptWord[],
  sourceIndex: number,
  sourceText: string,
  minScore: number,
  correctionDraft = "",
): FuzzyMatch[] {
  const threshold = clampFuzzyMinScore(minScore);
  const sourceNorm = normalizeWordToken(sourceText);
  if (!sourceNorm) return [];

  const correctionNorm = normalizeWordToken(correctionDraft);
  const matches: FuzzyMatch[] = [];

  for (let i = 0; i < words.length; i++) {
    if (i === sourceIndex) continue;
    const text = words[i]?.text ?? "";
    const targetNorm = normalizeWordToken(text);
    if (!targetNorm) continue;
    if (correctionNorm && targetNorm === correctionNorm) continue;

    const score = fuzzyWordScore(sourceText, text);
    if (score < threshold) continue;

    matches.push({
      index: i,
      text,
      score,
      start_ms: words[i].start_ms,
    });
  }

  return matches.sort((a, b) => b.score - a.score || a.start_ms - b.start_ms);
}
