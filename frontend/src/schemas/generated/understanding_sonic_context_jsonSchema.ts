// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_sonic_context_jsonSchema = z.object({
  "version": z.literal(1),
  "sonic_context_hash": z.string().optional(),
  "built_from": z.array(z.string()).optional(),
  "sparse_mode": z.boolean().optional(),
  "scenario": z.object({
  "format_class": z.string(),
  "tone_class": z.string(),
  "atlas_bucket": z.enum(["one_on_one", "panel", "fireside", "technical_deep_dive", "media_profile", "debate", "noisy_room", "dense_jargon", "trauma_adjacent"]),
  "sound_posture": z.object({
  "bed_density": z.enum(["none", "minimal", "sparse", "moderate"]),
  "stinger_cap_per_minute": z.number(),
}),
}),
  "sonic_identity_seed": z.object({
  "primary_mood": z.string(),
  "density_hint": z.string(),
  "room_character": z.string(),
}),
  "tag_registry": z.array(z.object({
  "tag_id": z.string().min(1),
  "kind": z.enum(["topic", "entity", "emotional", "theme", "acoustic"]),
  "keywords": z.array(z.string()).min(1),
  "segment_ids": z.array(z.string()).optional(),
  "emotional_valence": z.string().optional(),
  "confidence": z.number().optional(),
  "provenance": z.array(z.string()).min(1),
})),
  "cue_opportunities": z.array(z.object({
  "kind": z.enum(["chapter_boundary", "emotional_beat", "vo_bridge", "montage_transition", "laughter_window", "tension_peak", "cold_open", "outro"]),
  "segment_id": z.string().optional(),
  "from_clip_rank": z.number().optional(),
  "to_clip_rank": z.number().optional(),
  "beat": z.string().optional(),
  "start_ms": z.number().optional(),
  "end_ms": z.number().optional(),
  "confidence": z.number(),
  "provenance": z.array(z.string()).min(1),
})),
  "mix_policy": z.object({
  "underscore_policy": z.enum(["normal", "sparse", "sparse_or_skip", "skip"]),
  "adaptive_max_assets_flow1": z.number(),
  "adaptive_max_assets_flow2": z.number(),
  "stinger_cap_per_minute": z.number().optional(),
  "duration_bands_by_role": z.record(z.string(), z.unknown()),
}),
  "avoid_hard": z.array(z.string()),
  "segment_flags": z.object({
  "overlap_high": z.array(z.string()).optional(),
  "trauma_adjacent": z.array(z.string()).optional(),
  "jargon_dense": z.array(z.string()).optional(),
  "disfluency_restore": z.array(z.string()).optional(),
  "comprehension_risk": z.array(z.string()).optional(),
}),
  "value_features_summary": z.record(z.string(), z.unknown()).optional(),
});
