// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_selection_jsonSchema = z.object({
  "ordered_segment_ids": z.array(z.string()).min(1),
  "chapters": z.array(z.object({
  "title": z.string(),
  "segment_ids": z.array(z.string()),
})).optional(),
  "excluded_segment_ids": z.array(z.object({
  "segment_id": z.string(),
  "reason": z.string(),
})).optional(),
  "notes": z.string().optional(),
});
