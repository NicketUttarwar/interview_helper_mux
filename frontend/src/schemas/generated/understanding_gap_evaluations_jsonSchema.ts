// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_gap_evaluations_jsonSchema = z.object({
  "evaluations": z.array(z.object({
  "segment_id": z.string(),
  "self_explanatory": z.boolean(),
  "gap_type": z.string().nullable().optional(),
  "secondary_gap_type": z.string().nullable().optional(),
  "listener_confusion": z.string().optional(),
  "severity": z.enum(["low", "medium", "high"]).optional(),
  "recommended_framing": z.enum(["question", "summary", "preface", "bridge", "none"]).optional(),
  "candidate_for_summary": z.boolean().optional(),
  "supports_ranking_exclude": z.boolean().optional(),
  "duplicate_claim_cluster": z.string().optional(),
})),
});
