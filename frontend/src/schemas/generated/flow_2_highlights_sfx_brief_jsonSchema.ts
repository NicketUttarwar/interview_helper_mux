// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_2_highlights_sfx_brief_jsonSchema = z.object({
  "cold_open": z.record(z.string(), z.unknown()).optional(),
  "transitions": z.array(z.unknown()),
  "outro": z.record(z.string(), z.unknown()).optional(),
});
