// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_synthetic_framing_plan_jsonSchema = z.object({
  "selection_order_content_hash": z.string(),
  "strategy_summary": z.string().min(1),
  "synthetic_input_share_estimate": z.number(),
  "lines": z.array(z.object({
  "line_id": z.string().min(1),
  "role": z.string(),
  "placement": z.enum(["before_segment", "after_segment", "between_segments", "cold_open", "close"]),
  "anchor_segment_id": z.string(),
  "after_segment_id": z.string().nullable().optional(),
  "before_segment_id": z.string().nullable().optional(),
  "text": z.string().min(1),
  "duration_ratio": z.number(),
  "target_duration_ms": z.number(),
  "comprehension_reason": z.string().min(1),
  "native_respect_violation": z.literal(false),
  "speaker_policy": z.string().optional(),
})),
});
