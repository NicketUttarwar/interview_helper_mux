// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_speakers_jsonSchema = z.object({
  "speakers": z.array(z.object({
  "speaker_id": z.string(),
  "role": z.enum(["interviewer", "interviewee", "unknown"]),
  "confidence": z.number(),
  "evidence": z.array(z.string()).optional(),
})).min(1),
  "notes": z.string().nullable().optional(),
});
