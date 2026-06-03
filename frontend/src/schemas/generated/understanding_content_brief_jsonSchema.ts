// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_content_brief_jsonSchema = z.object({
  "thesis": z.string().min(1),
  "topics": z.array(z.object({
  "name": z.string(),
  "summary": z.string(),
  "approx_time_range": z.string().optional(),
  "segment_ids": z.array(z.string()).optional(),
  "confidence": z.number().optional(),
})),
  "key_claims": z.array(z.unknown()).optional(),
  "emotional_beats": z.array(z.unknown()).optional(),
  "audience": z.string().optional(),
  "jargon_glossary": z.array(z.unknown()).optional(),
});
