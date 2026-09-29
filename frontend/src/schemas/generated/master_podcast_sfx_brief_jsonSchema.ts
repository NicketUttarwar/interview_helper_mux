// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_podcast_sfx_brief_jsonSchema = z.object({
  "profile": z.literal("podcast"),
  "chapter_stingers": z.array(z.object({
  "after_chapter_id": z.string(),
  "mood": z.string(),
  "duration_ms": z.number(),
  "description": z.string(),
})).optional(),
  "beds": z.array(z.object({
  "start_segment_id": z.string(),
  "end_segment_id": z.string(),
  "mood": z.string(),
  "level_db": z.number(),
})).optional(),
  "bridges": z.array(z.object({
  "between_segment_ids": z.array(z.string()),
  "description": z.string(),
})).optional(),
});
