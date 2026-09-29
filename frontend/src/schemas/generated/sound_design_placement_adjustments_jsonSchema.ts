// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const sound_design_placement_adjustments_jsonSchema = z.object({
  "version": z.number().optional(),
  "adjustments": z.array(z.object({
  "asset_id": z.string(),
  "cue_id": z.string().optional(),
  "role": z.string().optional(),
  "action": z.string().optional(),
  "reason": z.string().optional(),
  "suggested_level_db_delta": z.number().optional(),
  "suggested_crossfade_ms": z.number().optional(),
  "provenance": z.object({
  "rule_id": z.string().optional(),
  "source_artifact": z.string().optional(),
  "detail": z.string().optional(),
}).optional(),
  "scenario_override": z.boolean().optional(),
  "adaptive_level_source": z.enum(["sap_percentile", "operator", "default", "mmaudio_qa"]).optional(),
})),
});
