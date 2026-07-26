// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_gap_report_jsonSchema = z.object({
  "interviewer_lines": z.array(z.object({
  "line_id": z.string().optional(),
  "gap_type": z.string(),
  "line_category": z.enum(["framing_question", "context_setup", "segment_summary", "episode_preface", "story_bridge", "extracted_context"]).optional(),
  "text": z.string(),
  "targets_segment_id": z.string(),
  "placement": z.enum(["before", "after"]),
  "delivery": z.enum(["record", "synthesize"]),
  "rationale": z.string().optional(),
  "voice_speaker_id": z.string().optional(),
  "supports_segment_ids": z.array(z.string()).optional(),
  "replaces_source_segments": z.array(z.string()).optional(),
  "estimated_duration_sec": z.number().optional(),
  "extracted_from": z.object({
  "artifact": z.string().optional(),
  "path": z.string().optional(),
}).optional(),
  "act_context": z.number().optional(),
  "suggested_tone": z.enum(["analytical", "consumer", "neutral"]).optional(),
  "trim_hint_ms": z.number().optional(),
  "severity": z.enum(["low", "medium", "high", "critical"]).optional(),
  "blocking": z.boolean().optional(),
  "skipped_optional": z.boolean().optional(),
})),
});
