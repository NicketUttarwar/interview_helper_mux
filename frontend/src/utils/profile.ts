import type { AnalysisState } from "../types";

export function themesToText(themes: AnalysisState["themes"]): string {
  return (themes || [])
    .map((t) => {
      const id = t.id || "";
      const label = t.label || "";
      const summary = (t.summary || "").replace(/\n/g, " ");
      return `${id} | ${label} | ${summary}`.trim();
    })
    .join("\n");
}

export function textToThemes(text: string): NonNullable<AnalysisState["themes"]> {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, i) => {
      const parts = line.split("|").map((p) => p.trim());
      if (parts.length >= 3) {
        return {
          id: parts[0] || `theme_${i + 1}`,
          label: parts[1],
          summary: parts.slice(2).join(" | "),
          segment_ids: [],
          confidence: 1,
          sources: ["operator"],
        };
      }
      return {
        id: `theme_${i + 1}`,
        label: line,
        summary: "",
        segment_ids: [],
        confidence: 1,
        sources: ["operator"],
      };
    });
}

export function questionsToText(
  questions: AnalysisState["major_questions"],
): string {
  return (questions || [])
    .map((q) => (typeof q === "string" ? q : q.question || ""))
    .filter(Boolean)
    .join("\n");
}

export function textToQuestions(text: string): Array<{
  question: string;
  segment_ids: string[];
  priority: string;
}> {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((question) => ({
      question,
      segment_ids: [],
      priority: "medium",
    }));
}

export function collectElevenLabsPromptEdits<
  T extends {
    elevenlabs_prompt?: string;
    negative_prompt?: string;
    prompt_influence?: number;
  },
>(
  originalRows: T[],
  getCardValues: (idx: number) => {
    promptText: string;
    negative: string;
    influenceRaw: string;
  },
): T[] {
  return originalRows.map((row, idx) => {
    const { promptText, negative, influenceRaw } = getCardValues(idx);
    const influence =
      influenceRaw !== undefined && influenceRaw !== ""
        ? Number(influenceRaw)
        : row.prompt_influence;
    return {
      ...row,
      elevenlabs_prompt: promptText.trim(),
      negative_prompt: negative.trim(),
      prompt_influence: Number.isFinite(influence)
        ? Math.min(1, Math.max(0, influence as number))
        : row.prompt_influence,
    };
  });
}

export function latestElevenLabsListenByAsset(
  listenResults: Array<{ asset_id?: string; result?: string; at?: string; note?: string }>,
): Map<string, { result?: string; at?: string; note?: string }> {
  const map = new Map<string, { result?: string; at?: string; note?: string }>();
  for (const row of listenResults || []) {
    if (row?.asset_id) map.set(row.asset_id, row);
  }
  return map;
}

export function collectElevenLabsGeneratedAssets(
  runAssets: Array<{ asset_id: string; path: string }> | undefined,
  stageAudioOutputs: string[] | undefined,
): Array<{ asset_id: string; path: string }> {
  const paths = new Map<string, string>();
  for (const a of runAssets || []) {
    if (a?.asset_id) {
      paths.set(a.asset_id, a.path || `sound_design/assets/${a.asset_id}.wav`);
    }
  }
  for (const p of stageAudioOutputs || []) {
    if (!/\.wav$/i.test(p)) continue;
    const base = p.split("/").pop()?.replace(/\.wav$/i, "") || "";
    if (base && !paths.has(base)) paths.set(base, p);
  }
  return [...paths.entries()].map(([asset_id, path]) => ({ asset_id, path }));
}
