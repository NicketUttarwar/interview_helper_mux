// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const segments_manifest_jsonSchema = z.object({
  "segments": z.array(z.object({
  "segment_id": z.string(),
  "type": z.enum(["interviewer_question", "interviewee_answer", "interviewer_reaction", "setup", "aside", "coda"]),
  "speaker_id": z.string(),
  "speaker_role": z.enum(["interviewer", "interviewee", "unknown"]),
  "topic_tags": z.array(z.string()),
  "flags": z.array(z.enum(["starts_mid_thought", "references_prior_missing", "heavy_crosstalk"])).optional(),
})).min(1),
});
