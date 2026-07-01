// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const segments_boundaries_jsonSchema = z.object({
  "boundaries": z.array(z.object({
  "segment_id": z.string(),
  "start_ms": z.number(),
  "end_ms": z.number(),
  "speaker_id": z.string().optional(),
  "proposed_split_reason": z.string(),
})).min(1),
  "warnings": z.array(z.string()).optional(),
});
