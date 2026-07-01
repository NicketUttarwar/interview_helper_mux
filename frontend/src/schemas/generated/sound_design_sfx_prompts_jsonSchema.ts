// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const sound_design_sfx_prompts_jsonSchema = z.object({
  "prompts": z.array(z.object({
  "asset_id": z.string().min(1),
  "sfx_prompt": z.string().min(1),
  "duration_seconds": z.number(),
  "negative_prompt": z.string().min(1),
  "prompt_influence": z.number().optional(),
  "role": z.string().optional(),
  "mmaudio_variant": z.enum(["small_16k", "small_44k", "medium_44k", "large_44k", "large_44k_v2"]).optional(),
  "cfg_strength": z.number().optional(),
  "num_steps": z.number().optional(),
  "seed": z.number().optional(),
  "regression_notes": z.string().optional(),
  "musical_intent": z.record(z.string(), z.unknown()).optional(),
})).min(1),
});
