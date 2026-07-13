// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_transitions_jsonSchema = z.object({
  "transitions": z.array(z.object({
  "after_segment_id": z.string(),
  "before_segment_id": z.string(),
  "text": z.string(),
  "type": z.string(),
})),
});
