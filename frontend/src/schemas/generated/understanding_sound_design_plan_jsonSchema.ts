// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_sound_design_plan_jsonSchema = z.object({
  "version": z.number(),
  "coherence": z.object({
  "sonic_identity": z.string(),
  "primary_mood": z.string(),
  "density": z.string(),
}),
  "palettes": z.array(z.object({
  "palette_id": z.string(),
  "theme_label": z.string(),
  "keywords": z.array(z.string()),
  "segment_ids": z.array(z.string()),
  "ambient_description": z.string(),
  "accent_description": z.string(),
  "avoid": z.array(z.string()),
})),
  "assets": z.array(z.object({
  "asset_id": z.string(),
  "role": z.string(),
  "palette_id": z.string().optional(),
  "description": z.string(),
  "duration_seconds": z.number(),
  "reuse_note": z.string().optional(),
})),
  "flow_plans": z.object({
  "flow1": z.object({
  "profile": z.string(),
  "cues": z.array(z.object({
  "cue_id": z.string(),
  "asset_id": z.string(),
  "placement": z.string(),
})),
}),
  "flow2": z.object({
  "profile": z.string(),
  "cues": z.array(z.object({
  "cue_id": z.string(),
  "asset_id": z.string(),
  "placement": z.string(),
})),
}),
}),
  "generated": z.record(z.string(), z.unknown()),
});
