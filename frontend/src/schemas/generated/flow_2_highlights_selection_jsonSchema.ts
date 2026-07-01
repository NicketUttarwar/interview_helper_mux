// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_2_highlights_selection_jsonSchema = z.object({
  "highlights": z.array(z.object({
  "rank": z.number(),
  "segment_id": z.string(),
  "start_ms": z.number(),
  "end_ms": z.number(),
  "headline": z.string(),
  "scores": z.object({
  "salience": z.number(),
  "clarity": z.number(),
  "emotion": z.number(),
  "quotability": z.number(),
  "diversity_bonus": z.number(),
}),
  "needs_interviewer_tag": z.boolean().optional(),
  "suggested_tag": z.string().nullable().optional(),
})).max(5),
  "rejected_candidates": z.array(z.object({
  "segment_id": z.string(),
  "reason": z.string(),
})).optional(),
  "reel_thesis": z.string(),
});
