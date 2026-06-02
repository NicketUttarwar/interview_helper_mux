export function stageDescriptionParts(description: string): {
  summary: string;
  detail: string | null;
} {
  const trimmed = description.trim();
  const sentenceEnd = trimmed.search(/\.\s+/);
  if (sentenceEnd > 0 && sentenceEnd < trimmed.length - 2) {
    return {
      summary: trimmed.slice(0, sentenceEnd + 1),
      detail: trimmed.slice(sentenceEnd + 2).trim() || null,
    };
  }
  if (trimmed.length > 140) {
    return {
      summary: `${trimmed.slice(0, 137)}…`,
      detail: trimmed,
    };
  }
  return { summary: trimmed, detail: null };
}
