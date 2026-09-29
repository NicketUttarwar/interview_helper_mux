// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_refinement_agenda_jsonSchema = z.object({
  "run_id": z.string(),
  "schema_version": z.number(),
  "phase": z.enum(["draft", "confirm"]),
  "decided_at": z.string().optional(),
  "tape_character": z.array(z.string()).optional(),
  "eligible_classes": z.array(z.string()),
  "ineligible_classes": z.array(z.object({
  "class_id": z.string().optional(),
  "reason": z.string().optional(),
})).optional(),
  "succession_hints": z.array(z.string()).optional(),
  "policy_pack_id": z.string().nullable().optional(),
  "prior_bias_applied": z.boolean().optional(),
  "north_star_notes": z.string().optional(),
});
