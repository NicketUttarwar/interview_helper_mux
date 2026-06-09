export interface TranscriptCorrectionStats {
  total: number;
  fuzzyBatch: number;
}

export function emptyCorrectionStats(): TranscriptCorrectionStats {
  return { total: 0, fuzzyBatch: 0 };
}

export function formatCorrectionSummary(stats: TranscriptCorrectionStats): string {
  if (stats.total <= 0) return "";
  if (stats.fuzzyBatch > 0) {
    return `Corrected ${stats.total} words (${stats.fuzzyBatch} via fuzzy batch)`;
  }
  return `Corrected ${stats.total} word${stats.total === 1 ? "" : "s"}`;
}

export function addCorrectionStats(
  stats: TranscriptCorrectionStats,
  totalAdded: number,
  fuzzyBatchAdded: number,
): TranscriptCorrectionStats {
  return {
    total: stats.total + totalAdded,
    fuzzyBatch: stats.fuzzyBatch + fuzzyBatchAdded,
  };
}
