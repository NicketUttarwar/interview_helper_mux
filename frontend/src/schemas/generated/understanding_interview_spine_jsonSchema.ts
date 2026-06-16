// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_interview_spine_jsonSchema = z.object({
  "schema_version": z.number(),
  "derived_from": z.object({
  "normalized_wav": z.string(),
  "normalized_wav_sha256": z.string().optional(),
  "transcript": z.string(),
  "transcript_sha256": z.string().optional(),
  "source_acoustic_profile": z.string().optional(),
  "source_acoustic_profile_sha256": z.string().optional(),
  "preclean_isolated": z.unknown().optional(),
  "preclean_isolated_sha256": z.unknown().optional(),
  "computed_at": z.string(),
  "stage": z.string(),
}),
  "encoders": z.object({
  "dsp": z.string().optional(),
  "clap": z.unknown().optional(),
  "ssl": z.unknown().optional(),
}),
  "window_policy": z.object({
  "window_sec": z.number(),
  "hop_sec": z.number(),
  "align_to": z.enum(["words"]),
}),
  "windows": z.array(z.object({
  "window_id": z.string(),
  "start_ms": z.number(),
  "end_ms": z.number(),
  "speaker_id": z.unknown().optional(),
  "text_span": z.string(),
  "features": z.object({
  "rms_p50": z.number().optional(),
  "pause_before_ms": z.number().optional(),
  "speaking_rate_wpm": z.number().optional(),
  "f0_median_hz": z.unknown().optional(),
}),
  "embedding_ref": z.unknown().optional(),
})),
  "boundary_events": z.array(z.object({
  "time_ms": z.number(),
  "type": z.enum(["silence_valley", "speaker_turn", "pause_ladder", "prosody_shift", "trust_dip", "novelty_hint", "topic_shift_hint"]),
  "confidence": z.number(),
  "sources": z.array(z.string()),
  "window_ids": z.array(z.string()).optional(),
})),
  "retrieval": z.object({
  "enabled": z.boolean(),
  "model_id": z.unknown().optional(),
  "sidecar_path": z.unknown().optional(),
  "vector_dim": z.unknown().optional(),
  "window_count": z.number().optional(),
}),
  "speaker_stats": z.array(z.object({
  "speaker_id": z.string(),
  "turn_count": z.number().optional(),
  "avg_wpm": z.number().optional(),
  "register_hint": z.string().optional(),
})),
});
