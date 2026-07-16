import type { StageInfo } from "../types";

const PATH_HINTS: Array<{ pattern: RegExp; label: string }> = [
  { pattern: /content_brief/i, label: "Thesis, topics, and narrative framing" },
  { pattern: /speakers\.json/i, label: "Speaker roles, format candidate, and gap sensitivity" },
  { pattern: /themes/i, label: "Theme clusters and story angles" },
  { pattern: /gap_report/i, label: "Missing context and pickup lines" },
  { pattern: /analysis_state/i, label: "Analysis profile and tone" },
  { pattern: /manifest\.json/i, label: "Segment list and classifications" },
  { pattern: /boundaries/i, label: "Topic boundaries" },
  { pattern: /selection\.json/i, label: "Episode order and clip selection" },
  { pattern: /edl\.json/i, label: "Edit decision list" },
  { pattern: /sound_design_plan/i, label: "Sound design plan cues" },
  { pattern: /sfx_prompts/i, label: "MMAudio prompt briefs" },
  { pattern: /show_description/i, label: "Show description copy" },
];

export function skimHintForPath(path: string): string {
  const base = path.split("/").pop() || path;
  for (const { pattern, label } of PATH_HINTS) {
    if (pattern.test(path)) return label;
  }
  return `Skim ${base.replace(/_/g, " ")}`;
}

export function handoffSkimBullets(
  paths: string[],
  stage?: StageInfo | null,
  max = 3,
): string[] {
  const fromChecks = (stage?.guidance?.artifact_checks || [])
    .filter((c) => c.status === "todo")
    .map((c) => c.label)
    .slice(0, max);
  if (fromChecks.length >= 2) return fromChecks.slice(0, max);

  const fromPaths = paths.map(skimHintForPath);
  const merged = [...fromChecks];
  for (const p of fromPaths) {
    if (!merged.includes(p) && merged.length < max) merged.push(p);
  }
  if (merged.length === 0 && paths.length) {
    return [`Review ${paths.length} generated file${paths.length === 1 ? "" : "s"}`];
  }
  return merged.slice(0, max);
}
