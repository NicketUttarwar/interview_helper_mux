// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_speakers_jsonSchema = z.object({
  "speakers": z.array(z.object({
  "speaker_id": z.string(),
  "role": z.enum(["interviewer", "interviewee", "moderator", "panelist", "co_host", "off_mic", "unknown"]),
  "narrative_function": z.enum(["storyteller", "frame", "reactor", "analytical_lens", "unknown"]).optional(),
  "confidence": z.number().nullable(),
  "label": z.string().nullable().optional(),
  "evidence": z.array(z.string()).optional(),
  "evidence_windows": z.array(z.object({
  "start_ms": z.number(),
  "end_ms": z.number(),
  "quote": z.string(),
})).nullable().optional(),
  "question_density": z.enum(["low", "medium", "high"]).optional(),
  "avg_turn_length_ms": z.number().nullable().optional(),
})).min(1),
  "notes": z.string().nullable().optional(),
  "conversation_profile": z.object({
  "format_class_candidate": z.enum(["one_on_one", "panel", "fireside", "technical_deep_dive", "media_profile", "debate"]).optional(),
  "format_confidence": z.number().optional(),
  "tone_class_candidate": z.enum(["journalistic", "conversational", "investor", "technical", "human_interest"]).optional(),
  "dynamics": z.object({
  "question_density": z.enum(["low", "medium", "high"]).optional(),
  "turn_asymmetry": z.enum(["low", "medium", "high"]).optional(),
  "overlap_risk": z.enum(["low", "medium", "high"]).optional(),
}).optional(),
}).nullable().optional(),
  "conversation_hypotheses": z.array(z.object({
  "id": z.string(),
  "format_class": z.enum(["one_on_one", "panel", "fireside", "technical_deep_dive", "media_profile", "debate"]),
  "confidence": z.number(),
  "reason": z.string().optional(),
  "speaker_role_map": z.record(z.string(), z.unknown()).optional(),
  "blocking": z.boolean().optional(),
})).nullable().optional(),
  "confirmed_conversation_hypothesis_id": z.string().nullable().optional(),
  "role_tape_conflict": z.object({
  "blocking": z.boolean().optional(),
  "conflict_count": z.number().optional(),
  "typed_qa_count": z.number().optional(),
  "conflict_ratio": z.number().optional(),
  "examples": z.array(z.record(z.string(), z.unknown())).optional(),
}).nullable().optional(),
  "gap_sensitivity": z.object({
  "format_class": z.string().optional(),
  "tone_class": z.string().optional(),
  "severity_hints": z.object({
  "missing_question": z.enum(["strict", "normal", "relaxed"]).optional(),
  "missing_setup": z.enum(["strict", "normal", "relaxed"]).optional(),
  "missing_callback": z.enum(["strict", "normal", "relaxed"]).optional(),
  "missing_definition": z.enum(["strict", "normal", "relaxed"]).optional(),
  "missing_followup": z.enum(["strict", "normal", "relaxed"]).optional(),
  "ok_with_light_bridge": z.enum(["strict", "normal", "relaxed"]).optional(),
}).optional(),
  "priority_gap_types": z.array(z.string()).optional(),
  "deemphasize_gap_types": z.array(z.string()).optional(),
  "theme_overlays": z.array(z.object({
  "axis": z.string().optional(),
  "effect": z.string().optional(),
})).optional(),
  "segment_focus": z.string().optional(),
  "flow_hints": z.string().optional(),
  "notes": z.string().optional(),
}).nullable().optional(),
});
