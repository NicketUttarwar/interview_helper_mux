// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const sound_design_elevenlabs_prompts_jsonSchema = z.object({
  "prompts": z.array(z.object({
  "asset_id": z.string().min(1),
  "elevenlabs_prompt": z.string().min(1),
  "duration_seconds": z.number(),
  "negative_prompt": z.string().min(1),
  "prompt_influence": z.number().optional(),
  "musical_intent": z.record(z.string(), z.unknown()).optional(),
})),
});
