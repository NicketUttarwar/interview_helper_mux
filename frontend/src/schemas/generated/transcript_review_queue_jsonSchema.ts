// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const transcript_review_queue_jsonSchema = z.object({
  "version": z.number().optional(),
  "low_confidence_threshold": z.number().optional(),
  "sort_mode": z.enum(["salience", "confidence"]).optional(),
  "chunk_count": z.number().optional(),
  "chunks": z.array(z.object({
  "chunk_id": z.string(),
  "rank": z.number(),
  "start_ms": z.number(),
  "end_ms": z.number(),
  "speaker_id": z.string().optional(),
  "text": z.string(),
  "corrected_text": z.string().optional(),
  "confidence": z.number(),
  "word_count": z.number().optional(),
  "needs_review": z.boolean().optional(),
  "reviewed": z.boolean().optional(),
  "clip_path": z.string().optional(),
  "clip_start_ms": z.number().optional(),
  "clip_end_ms": z.number().optional(),
  "acoustic_stress_score": z.number().optional(),
})),
});
