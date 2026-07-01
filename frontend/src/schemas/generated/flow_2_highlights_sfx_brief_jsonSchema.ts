// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_2_highlights_sfx_brief_jsonSchema = z.object({
  "cold_open": z.object({
  "duration_ms": z.number().optional(),
  "description": z.string().optional(),
  "mood": z.string().optional(),
}).optional(),
  "transitions": z.array(z.object({
  "from_clip_rank": z.number(),
  "to_clip_rank": z.number(),
  "duration_ms": z.number(),
  "sfx_types": z.array(z.string()).optional(),
  "description": z.string(),
  "duck_under_speech_db": z.number().optional(),
})).min(0),
  "outro": z.object({
  "duration_ms": z.number().optional(),
  "description": z.string().optional(),
}).optional(),
});
