// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const mastering_media_ip_cta_jsonSchema = z.object({
  "version": z.literal(1),
  "locked": z.boolean().optional(),
  "judgments": z.array(z.record(z.string(), z.unknown())).optional(),
  "dropped_segment_ids": z.array(z.string()).optional(),
  "never_touch_segment_ids": z.array(z.string()).optional(),
  "never_touch_texts": z.array(z.string()).optional(),
  "cover_target_ids": z.array(z.string()).optional(),
  "recuts": z.array(z.record(z.string(), z.unknown())).optional(),
  "cta_open_parent": z.string().nullable().optional(),
  "open_choice": z.string().nullable().optional(),
  "notes": z.array(z.string()).optional(),
});
