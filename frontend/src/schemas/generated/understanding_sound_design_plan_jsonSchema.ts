// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_sound_design_plan_jsonSchema = z.object({
  "version": z.literal(1),
  "coherence": z.object({
  "sonic_identity": z.string(),
  "primary_mood": z.string(),
  "density": z.string(),
  "scenario_bucket": z.string().optional(),
  "tag_lineage": z.array(z.string()).optional(),
  "sonic_context_hash": z.string().optional(),
}),
  "palettes": z.array(z.object({
  "palette_id": z.string(),
  "theme_label": z.string(),
  "keywords": z.array(z.string()),
  "segment_ids": z.array(z.string()),
  "ambient_description": z.string(),
  "accent_description": z.string(),
  "avoid": z.array(z.string()),
  "tag_ids": z.array(z.string()).optional(),
  "sonic_bucket": z.enum(["ambient_territory", "accent_texture", "transition_family"]).optional(),
})),
  "assets": z.array(z.object({
  "asset_id": z.string(),
  "role": z.string(),
  "palette_id": z.string().optional(),
  "description": z.string(),
  "duration_seconds": z.number(),
  "reuse_note": z.string().optional(),
  "generation_notes": z.string().optional(),
  "tag_ids": z.array(z.string()).optional(),
  "scenario_constraints": z.array(z.string()).optional(),
  "cue_opportunity_refs": z.array(z.string()).optional(),
})),
  "flow_plans": z.object({
  "podcast": z.object({
  "profile": z.string(),
  "cues": z.array(z.object({
  "cue_id": z.string(),
  "asset_id": z.string(),
  "placement": z.string(),
})),
}),
}),
  "generated": z.record(z.string(), z.unknown()),
  "motif_family": z.object({
  "motif_id": z.string().optional(),
  "genre_hint": z.string().optional(),
  "instrumentation": z.array(z.string()).optional(),
  "scale_or_mode": z.string().optional(),
  "tempo_bpm_feel": z.string().optional(),
  "time_feel": z.string().optional(),
  "motif_phrase": z.string().optional(),
  "mood": z.string().optional(),
  "energy_curve_by_act": z.array(z.unknown()).optional(),
  "prompt_dna": z.string().optional(),
  "stems": z.array(z.string()).optional(),
  "palette_counts": z.record(z.string(), z.unknown()).optional(),
}).optional(),
  "palette_counts": z.record(z.string(), z.unknown()).optional(),
  "_meta": z.record(z.string(), z.unknown()).optional(),
});
