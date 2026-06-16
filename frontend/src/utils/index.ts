export {
  correctionDiffersFromSource,
  FUZZY_MATCH_DEFAULT,
  FUZZY_MATCH_FLOOR,
  clampFuzzyMinScore,
  findFuzzyWordMatches,
  fuzzyWordScore,
  normalizeWordToken,
  type FuzzyMatch,
} from "./fuzzyMatch";

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatMs(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export function formatTs(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function escapeHtml(s: string): string {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function parseLogDetail(
  detail?: string | Record<string, unknown> | null,
): Record<string, unknown> | null {
  if (!detail) return null;
  if (typeof detail === "object") return detail;
  try {
    return JSON.parse(detail) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function isJsonArtifactPath(path: string): boolean {
  return path.endsWith(".json");
}

export function formatValueMetric(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "number")
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value);
}

export function formatValueTags(
  tags?: Record<string, string[]>,
): string[] {
  if (!tags || typeof tags !== "object") return [];
  return ["LEX", "COM", "CRE"].flatMap((axis) => {
    const items = tags[axis];
    if (!Array.isArray(items) || !items.length) return [];
    return items.map((t) => `${axis}:${t}`);
  });
}

export function nleHasOperatorEdits(nle: Record<string, unknown> | null): boolean {
  if (!nle || typeof nle !== "object") return false;
  const order = nle.sequence_order;
  if (Array.isArray(order) && order.length) return true;
  const overrides = nle.segment_overrides;
  if (!overrides || typeof overrides !== "object") return false;
  return Object.values(overrides).some((ov) => {
    if (!ov || typeof ov !== "object") return false;
    const o = ov as Record<string, unknown>;
    return (
      o.excluded ||
      o.mark_redo ||
      o.start_ms != null ||
      o.end_ms != null ||
      o.split_into
    );
  });
}

export function mapGateToStage(id: string): string {
  if (id === "transcript_review") return "transcript_review_build";
  if (id === "g1_vo_pickup" || id === "g2_flow_select") return "optimal_questions";
  return id;
}

/** External APIs are assumed configured and consented at session start. */
export const ALL_API_CONSENTS: Record<string, boolean> = {
  openai: true,
  aws: true,
  
};

export const VALUE_FEATURES_PATH = "understanding/value_features.json";
export const SAP_PATH = "understanding/source_acoustic_profile.json";
export const SPINE_PATH = "understanding/interview_spine.json";
export const COHERENCE_REPORT_PATH = "understanding/coherence_report.json";

export const PACE_CLASS_OPTIONS = ["", "calm", "conversational", "brisk", "dense"];
export const UNDERSCORE_POLICY_OPTIONS = ["", "normal", "sparse", "skip"];
