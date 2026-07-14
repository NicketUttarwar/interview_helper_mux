// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_edl_jsonSchema = z.object({
  "version": z.literal(1),
  "ordered_segment_ids": z.array(z.string()),
  "clips": z.array(z.unknown()),
  "gap_placements": z.array(z.unknown()).optional(),
  "timeline_duration_ms": z.number(),
  "disfluency_clip_count": z.number().optional(),
  "disfluency_restore_enabled": z.boolean().optional(),
  "mux_scope": z.string().optional(),
});
