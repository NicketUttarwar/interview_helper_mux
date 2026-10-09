// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_interview_spine_jsonSchema = z.object({
  "schema_version": z.literal(1),
  "derived_from": z.object({
  "normalized_wav": z.string(),
  "normalized_wav_sha256": z.string().optional(),
  "transcript": z.string(),
  "transcript_sha256": z.string().optional(),
  "source_acoustic_profile": z.string().optional(),
  "source_acoustic_profile_sha256": z.string().optional(),
  "preclean_isolated": z.string().nullable().optional(),
  "preclean_isolated_sha256": z.string().nullable().optional(),
  "computed_at": z.string(),
  "stage": z.literal("interview_spine_build"),
}),
  "encoders": z.object({
  "dsp": z.string().optional(),
  "clap": z.string().nullable().optional(),
  "ssl": z.string().nullable().optional(),
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
  "speaker_id": z.string().nullable().optional(),
  "text_span": z.string(),
  "features": z.object({
  "rms_p50": z.number().optional(),
  "pause_before_ms": z.number().optional(),
  "speaking_rate_wpm": z.number().optional(),
  "f0_median_hz": z.number().nullable().optional(),
}),
  "embedding_ref": z.number().nullable().optional(),
})),
  "boundary_events": z.array(z.object({
  "time_ms": z.number(),
  "type": z.enum(["silence_valley", "speaker_turn", "pause_ladder", "prosody_shift", "trust_dip", "novelty_hint", "topic_shift_hint"]),
  "confidence": z.number(),
  "sources": z.array(z.string()).min(1),
  "window_ids": z.array(z.string()).optional(),
})),
  "retrieval": z.object({
  "enabled": z.boolean(),
  "model_id": z.string().nullable().optional(),
  "sidecar_path": z.string().nullable().optional(),
  "vector_dim": z.number().nullable().optional(),
  "window_count": z.number().optional(),
}),
  "speaker_stats": z.array(z.object({
  "speaker_id": z.string(),
  "turn_count": z.number().optional(),
  "avg_wpm": z.number().optional(),
  "register_hint": z.string().optional(),
})),
});
