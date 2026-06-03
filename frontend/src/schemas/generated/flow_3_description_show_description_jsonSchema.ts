// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_3_description_show_description_jsonSchema = z.object({
  "title_suggestion": z.string().min(3).optional(),
  "description_markdown": z.string().min(400),
  "word_count": z.number(),
  "hook_sentence": z.string().min(10),
  "themes_highlighted": z.array(z.string().min(2)),
  "audience_pitch": z.string().min(10),
  "evidence_segment_ids": z.array(z.string()),
  "tone": z.enum(["journalistic", "conversational", "investor", "technical", "human_interest"]),
  "confidence": z.number(),
});
