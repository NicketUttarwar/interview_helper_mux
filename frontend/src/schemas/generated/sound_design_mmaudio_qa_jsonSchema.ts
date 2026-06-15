// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const sound_design_mmaudio_qa_jsonSchema = z.object({
  "version": z.number(),
  "assets": z.array(z.object({
  "asset_id": z.string(),
  "role": z.string().optional(),
  "verdict": z.enum(["pass", "warn", "fail"]),
  "generation_status": z.enum(["pass", "failed", "placeholder"]).optional(),
  "reasons": z.array(z.string()).optional(),
  "action": z.string().optional(),
  "actual_duration_seconds": z.number().optional(),
  "suggested_trim_ms": z.number().optional(),
  "suggested_level_db_delta": z.number().optional(),
  "suggested_crossfade_ms": z.number().optional(),
  "suggested_cfg_delta": z.number().optional(),
  "speech_band_ratio": z.number().optional(),
  "theme_fit_score": z.number().optional(),
  "loop_seam_score": z.number().optional(),
  "silence_detected": z.boolean().optional(),
  "spectral_bucket_match": z.boolean().optional(),
  "semantic_similarity": z.number().optional(),
  "semantic_qa_verdict": z.enum(["pass", "warn", "fail", "skipped"]).optional(),
  "semantic_qa_skipped_reason": z.string().optional(),
  "semantic_qa_model_id": z.string().optional(),
  "semantic_qa_threshold": z.number().optional(),
  "recommended_action": z.enum(["pass", "refine", "regenerate", "trim_hint"]).optional(),
})),
});
