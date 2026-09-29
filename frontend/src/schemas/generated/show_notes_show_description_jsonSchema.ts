// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const show_notes_show_description_jsonSchema = z.object({
  "title_suggestion": z.string().min(3).max(120).optional(),
  "description_markdown": z.string().min(400).max(4000),
  "word_count": z.number(),
  "hook_sentence": z.string().min(10).max(300),
  "themes_highlighted": z.array(z.string().min(2)).min(1).max(6),
  "audience_pitch": z.string().min(10).max(400),
  "evidence_segment_ids": z.array(z.string()).min(1).max(24),
  "tone": z.enum(["journalistic", "conversational", "investor", "technical", "human_interest"]),
  "confidence": z.number(),
});
