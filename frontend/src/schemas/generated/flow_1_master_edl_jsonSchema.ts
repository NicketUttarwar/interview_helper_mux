// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_1_master_edl_jsonSchema = z.object({
  "version": z.number(),
  "ordered_segment_ids": z.array(z.string()),
  "clips": z.array(z.unknown()),
  "gap_placements": z.array(z.unknown()).optional(),
  "timeline_duration_ms": z.number(),
  "mux_scope": z.string().optional(),
});
