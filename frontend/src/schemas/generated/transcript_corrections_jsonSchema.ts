// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const transcript_corrections_jsonSchema = z.object({
  "corrections": z.record(z.string(), z.unknown()),
});
