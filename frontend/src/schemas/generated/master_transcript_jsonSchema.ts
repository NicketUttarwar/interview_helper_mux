// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_transcript_jsonSchema = z.object({
  "schema_version": z.literal(1),
  "timebase": z.literal("master"),
  "generated_at": z.string().optional(),
  "source_edl": z.string().optional(),
  "cue_count": z.number().optional(),
  "cues": z.array(z.object({
  "start_ms": z.number(),
  "end_ms": z.number(),
  "speaker_id": z.string().optional(),
  "speaker_name": z.string(),
  "text": z.string(),
  "kind": z.enum(["speech", "vo_pickup", "transition"]).optional(),
  "asset_id": z.string().optional(),
})),
});
