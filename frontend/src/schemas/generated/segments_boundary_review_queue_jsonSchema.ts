// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const segments_boundary_review_queue_jsonSchema = z.object({
  "version": z.number(),
  "generated_at": z.string().optional(),
  "low_confidence_threshold": z.number().optional(),
  "item_count": z.number().optional(),
  "items": z.array(z.object({
  "item_id": z.string(),
  "rank": z.number(),
  "segment_id": z.string(),
  "neighbor_segment_id": z.string().optional(),
  "edge": z.enum(["start", "end", "seam"]),
  "time_ms": z.number(),
  "original_ms": z.number().optional(),
  "suggested_ms": z.number().optional(),
  "overall": z.number(),
  "grade": z.enum(["high", "medium", "low", "reject"]),
  "reasons": z.array(z.string()).optional(),
  "left_text": z.string().optional(),
  "right_text": z.string().optional(),
  "repaired": z.boolean().optional(),
  "needs_review": z.boolean().optional(),
  "kind": z.string().optional(),
})),
});
