// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_junction_feel_audit_jsonSchema = z.object({
  "version": z.literal(1),
  "verdict": z.enum(["pass", "soft_pass", "fail", "remux_suggested", "unavailable"]).optional(),
  "skipped": z.boolean().optional(),
  "reason": z.string().optional(),
  "findings": z.array(z.record(z.string(), z.unknown())).optional(),
  "directives": z.array(z.object({
  "action": z.enum(["nudge_source_bounds", "insert_impact_hold", "clamp_air", "adjust_music_fade", "adjust_crossfade", "exclude_micro", "retarget_vo_anchor"]),
  "segment_id": z.string().nullable().optional(),
  "clip_index": z.number().nullable().optional(),
  "severity": z.string().optional(),
  "evidence": z.string().optional(),
  "detail": z.record(z.string(), z.unknown()).optional(),
})).optional(),
  "applied_directives": z.array(z.record(z.string(), z.unknown())).optional(),
  "llm_calls": z.number().optional(),
  "remaster_round": z.number().optional(),
  "error": z.string().nullable().optional(),
  "generated_at": z.string(),
});
