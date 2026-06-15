import type { SfxBlockReason, SfxPromptsResponse } from "../types";

const BLOCK_KIND_LABELS: Record<SfxBlockReason["kind"], string> = {
  g1_5: "Prompt approval (G1.5)",
  qa_fail: "MMAudio QA failed",
  spend: "Spend / artifact gate",
  venv: "Local MMAudio venv",
};

export function sfxBlockKindLabel(kind: SfxBlockReason["kind"]): string {
  return BLOCK_KIND_LABELS[kind] || kind;
}

function normalizeBlockReason(raw: string | SfxBlockReason): SfxBlockReason | null {
  if (typeof raw === "string") {
    const lower = raw.toLowerCase();
    let kind: SfxBlockReason["kind"] = "spend";
    if (lower.includes("g1.5") || lower.includes("approval")) kind = "g1_5";
    else if (lower.includes("qa") || lower.includes("mmaudio_qa")) kind = "qa_fail";
    else if (lower.includes("venv") || lower.includes("mmaudio")) kind = "venv";
    return { kind, message: raw };
  }
  if (raw?.kind && raw?.message) return raw;
  return null;
}

export function collectSfxBlockReasons(data: SfxPromptsResponse | null): SfxBlockReason[] {
  if (!data) return [];
  const out: SfxBlockReason[] = [];
  const seen = new Set<string>();

  const push = (reason: SfxBlockReason) => {
    const key = `${reason.kind}:${reason.message}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(reason);
  };

  for (const raw of data.block_reasons || []) {
    const norm = normalizeBlockReason(raw);
    if (norm) push(norm);
  }

  if (data.review_required && !data.review?.approved) {
    push({
      kind: "g1_5",
      message: "Review and approve crafted prompts before SFX generation.",
    });
  }

  const qaFails = (data.mmaudio_qa?.assets || []).filter(
    (row) =>
      row?.asset_id &&
      (row.verdict === "fail" ||
        row.generation_status === "failed" ||
        row.generation_status === "placeholder"),
  );
  if (qaFails.length) {
    push({
      kind: "qa_fail",
      message: "Deterministic MMAudio QA reported failures.",
      asset_ids: qaFails.map((r) => r.asset_id!).filter(Boolean),
    });
  }

  for (const warning of data.warnings || []) {
    const lower = warning.toLowerCase();
    if (lower.includes("venv") || lower.includes("bootstrap")) {
      push({ kind: "venv", message: warning });
    } else if (
      lower.includes("incomplete") ||
      lower.includes("spend gate") ||
      lower.includes("missing")
    ) {
      push({ kind: "spend", message: warning });
    }
  }

  if (!data.can_generate && !out.some((r) => r.kind === "g1_5")) {
    push({
      kind: "spend",
      message: "SFX generation is blocked until upstream craft artifacts are complete.",
    });
  }

  return out;
}
