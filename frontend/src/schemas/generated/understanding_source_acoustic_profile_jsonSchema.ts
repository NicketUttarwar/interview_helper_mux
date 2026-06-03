// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_source_acoustic_profile_jsonSchema = z.object({
  "schema_version": z.number(),
  "derived_from": z.object({
  "normalized_wav": z.string(),
  "normalized_wav_sha256": z.string().optional(),
  "transcript": z.string(),
  "transcript_sha256": z.string().optional(),
  "preclean_isolated": z.unknown().optional(),
  "preclean_isolated_sha256": z.unknown().optional(),
  "computed_at": z.string(),
  "stage": z.string(),
}),
  "pacing": z.object({
  "global_wpm": z.number(),
  "wpm_by_quartile": z.array(z.number()),
  "pause_p50_ms": z.number().optional(),
  "pause_p90_ms": z.number().optional(),
  "phrase_boundary_density_per_min": z.number().optional(),
  "overlap_proxy": z.number().optional(),
  "speech_active_ratio": z.number().optional(),
  "pace_class": z.enum(["calm", "conversational", "brisk", "dense"]),
}),
  "energy": z.object({
  "loudness_p10_lufs": z.number().optional(),
  "loudness_p50_lufs": z.number().optional(),
  "loudness_p90_lufs": z.number().optional(),
  "dynamic_range_db": z.number().optional(),
  "silence_ratio": z.number().optional(),
  "room_timbre_hint": z.string().min(1),
}),
  "prosody_summary": z.record(z.string(), z.unknown()).optional(),
  "source_music_risk": z.enum(["low", "medium", "high"]).optional(),
  "mix_contract": z.object({
  "bed_level_db_range": z.array(z.number()).optional(),
  "duck_under_speech_db": z.number().optional(),
  "stinger_max_per_minute": z.number().optional(),
  "midrange_policy": z.string().optional(),
  "rhythmic_presence_default": z.string().optional(),
  "tempo_feel_bpm": z.unknown().optional(),
  "underscore_policy": z.enum(["normal", "sparse", "skip"]),
}),
  "prompt_tokens": z.object({
  "bed": z.string().optional(),
  "stinger": z.string().optional(),
  "avoid": z.string().optional(),
  "density": z.string().optional(),
}),
  "placement_hints": z.record(z.string(), z.unknown()),
  "operator_overrides": z.record(z.string(), z.unknown()),
});
