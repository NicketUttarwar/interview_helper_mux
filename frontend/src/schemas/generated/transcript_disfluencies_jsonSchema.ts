// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const transcript_disfluencies_jsonSchema = z.object({
  "schema_version": z.literal(1),
  "status": z.enum(["ready", "skipped", "no_assets", "disabled"]),
  "skip_reason": z.string().optional(),
  "computed_at": z.string().optional(),
  "model": z.object({
  "vad": z.string().nullable().optional(),
  "whisper": z.string().nullable().optional(),
}).optional(),
  "events": z.array(z.object({
  "event_id": z.string(),
  "start_ms": z.number(),
  "end_ms": z.number(),
  "speaker_id": z.string().optional(),
  "text": z.string().optional(),
  "label": z.string().optional(),
  "confidence": z.number().optional(),
  "source": z.enum(["vad_gap", "transcript_lexicon"]).optional(),
  "clip_path": z.string().optional(),
  "review_status": z.enum(["pending", "confirmed", "rejected"]),
  "include_in_restore": z.boolean().optional(),
})),
  "stats": z.object({
  "total": z.number().optional(),
  "pending": z.number().optional(),
  "confirmed": z.number().optional(),
  "rejected": z.number().optional(),
}),
});
