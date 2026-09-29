// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const segments_nle_edits_jsonSchema = z.object({
  "playhead_ms": z.number().optional(),
  "zoom": z.number().optional(),
  "sequence_order": z.array(z.string()).optional(),
  "segment_overrides": z.record(z.string(), z.unknown()).optional(),
  "markers": z.array(z.record(z.string(), z.unknown())).optional(),
});
