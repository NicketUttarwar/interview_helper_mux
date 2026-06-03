// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_1_master_selection_jsonSchema = z.object({
  "ordered_segment_ids": z.array(z.string()),
  "chapters": z.array(z.unknown()).optional(),
  "excluded_segment_ids": z.array(z.unknown()).optional(),
  "notes": z.string().optional(),
});
