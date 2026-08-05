// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_edl_jsonSchema = z.object({
  "version": z.literal(1),
  "ordered_segment_ids": z.array(z.string()),
  "clips": z.array(z.unknown()),
  "gap_placements": z.array(z.unknown()).optional(),
  "timeline_duration_ms": z.number(),
  "silence_clip_count": z.number().optional(),
  "vo_pickup_clip_count": z.number().optional(),
  "transition_clip_count": z.number().optional(),
  "gap_report_line_count": z.number().optional(),
  "disfluency_clip_count": z.number().optional(),
  "disfluency_restore_enabled": z.boolean().optional(),
  "warnings": z.record(z.string(), z.unknown()).optional(),
  "mux_scope": z.string().optional(),
  "order_content_hash": z.string().optional(),
});
