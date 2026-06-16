// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_coherence_report_jsonSchema = z.object({
  "schema_version": z.number(),
  "derived_from": z.object({
  "interview_spine_sha256": z.string().optional(),
  "content_brief_sha256": z.string().optional(),
  "manifest_sha256": z.string().optional(),
  "duration_ms": z.number(),
  "computed_at": z.string(),
  "phase": z.enum(["post_content_context", "post_reanchor", "post_coverage"]),
}),
  "gate": z.object({
  "min_duration_ms": z.number(),
  "activated": z.boolean(),
  "duration_ms": z.number(),
}),
  "scores": z.array(z.object({
  "window_id": z.string(),
  "start_ms": z.number(),
  "end_ms": z.number(),
  "novelty_score": z.number().optional(),
  "theme_alignment": z.number().optional(),
  "best_theme_id": z.unknown().optional(),
  "drift_score": z.number().optional(),
})),
  "risks": z.array(z.object({
  "risk_id": z.string(),
  "kind": z.enum(["topic_drift", "claim_contradiction", "missing_callback"]),
  "time_ms": z.number(),
  "window_id": z.unknown().optional(),
  "theme_id": z.unknown().optional(),
  "claim_id": z.unknown().optional(),
  "confidence": z.number(),
  "blocking": z.boolean().optional(),
  "evidence": z.record(z.string(), z.unknown()),
  "suggested_action": z.record(z.string(), z.unknown()).optional(),
  "status": z.enum(["open", "resolved"]).optional(),
})),
  "summary": z.object({
  "topic_drift_count": z.number(),
  "claim_contradiction_count": z.number(),
  "missing_callback_count": z.number(),
  "phase": z.string().optional(),
}),
});
