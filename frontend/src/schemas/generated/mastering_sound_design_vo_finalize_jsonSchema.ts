// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const mastering_sound_design_vo_finalize_jsonSchema = z.object({
  "skipped": z.boolean(),
  "refused": z.boolean(),
  "reason": z.string().optional(),
  "adjusted": z.number().optional(),
  "skipped_cues": z.number().optional(),
  "missing": z.array(z.string()).optional(),
  "errors": z.array(z.string()).optional(),
});
