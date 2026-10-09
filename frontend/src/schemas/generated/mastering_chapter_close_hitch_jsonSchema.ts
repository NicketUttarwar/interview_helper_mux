// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const mastering_chapter_close_hitch_jsonSchema = z.object({
  "version": z.literal(1),
  "status": z.enum(["running", "committed"]),
  "seq": z.number().optional(),
  "skipped": z.boolean().optional(),
  "reason": z.string().optional(),
  "generated_at": z.string().optional(),
  "any_end_changed": z.boolean().optional(),
  "remap_count": z.number().optional(),
  "rewritten": z.array(z.string()).optional(),
  "restaged": z.array(z.string()).optional(),
  "unmatched_must_keep_ids": z.array(z.string()).optional(),
  "chapter_authority": z.record(z.string(), z.unknown()).optional(),
});
