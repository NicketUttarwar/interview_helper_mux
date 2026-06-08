// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_analysis_state_jsonSchema = z.object({
  "schema_version": z.number(),
  "run_id": z.string().optional(),
  "meta": z.object({
  "operator_verified": z.boolean().optional(),
  "last_updated_stage": z.string().optional(),
  "analysis_pass": z.number().optional(),
}).optional(),
  "interview_identity": z.object({
  "title": z.string().optional(),
  "one_line_summary": z.string().optional(),
  "source_audio_note": z.string().optional(),
}).optional(),
  "themes": z.array(z.object({
  "id": z.string().optional(),
  "label": z.string().optional(),
  "summary": z.string().optional(),
  "segment_ids": z.array(z.string()).optional(),
  "confidence": z.number().optional(),
  "sources": z.array(z.string()).optional(),
})),
  "major_questions": z.array(z.object({
  "question": z.string().optional(),
  "segment_ids": z.array(z.unknown()).optional(),
  "priority": z.enum(["high", "medium", "low"]).optional(),
})),
  "style": z.object({
  "tone": z.string().optional(),
  "pacing": z.string().optional(),
  "format_notes": z.string().optional(),
  "interviewer_style": z.string().optional(),
  "interviewee_style": z.string().optional(),
}),
  "narrative": z.object({
  "thesis": z.string().optional(),
  "audience": z.string().optional(),
  "emotional_beats": z.array(z.unknown()).optional(),
  "key_claims": z.array(z.unknown()).optional(),
  "topic_relationships": z.array(z.object({
  "from_topic": z.string().optional(),
  "to_topic": z.string().optional(),
  "relation": z.enum(["supports", "contradicts", "prerequisite", "example_of", "returns_to"]).optional(),
  "description": z.string().optional(),
  "evidence_segment_ids": z.array(z.string()).optional(),
})).optional(),
}),
  "entities": z.array(z.unknown()).optional(),
  "speakers": z.array(z.unknown()).optional(),
  "hypotheses": z.array(z.unknown()).optional(),
  "open_questions": z.array(z.unknown()).optional(),
  "operator_notes": z.string().optional(),
  "completion": z.object({
  "analysis_ready": z.boolean().optional(),
  "blockers": z.array(z.string()).optional(),
}).optional(),
});
