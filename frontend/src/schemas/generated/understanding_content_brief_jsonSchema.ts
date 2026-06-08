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
  "topic_relationships": z.array(z.object({
  "from_topic": z.string(),
  "to_topic": z.string(),
  "relation": z.enum(["supports", "contradicts", "prerequisite", "example_of", "returns_to"]),
  "description": z.string().optional(),
  "evidence_segment_ids": z.array(z.string()).optional(),
})).optional(),
  "key_claims": z.array(z.object({
  "id": z.string().optional(),
  "claim": z.string(),
  "claim_type": z.enum(["fact", "opinion", "prediction", "anecdote", "definition"]).optional(),
  "speaker_role": z.enum(["interviewee", "interviewer"]).optional(),
  "segment_ids": z.array(z.string()).optional(),
  "evidence_segment_ids": z.array(z.string()).optional(),
  "depends_on_claim_ids": z.array(z.string()).optional(),
})).optional(),
  "emotional_beats": z.array(z.unknown()).optional(),
  "audience": z.string().optional(),
  "jargon_glossary": z.array(z.unknown()).optional(),
});
