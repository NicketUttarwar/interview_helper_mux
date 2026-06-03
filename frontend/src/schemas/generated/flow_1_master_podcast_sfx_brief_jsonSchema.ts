// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_1_master_podcast_sfx_brief_jsonSchema = z.object({
  "profile": z.unknown(),
  "chapter_stingers": z.array(z.unknown()).optional(),
  "beds": z.array(z.unknown()).optional(),
  "bridges": z.array(z.unknown()).optional(),
});
