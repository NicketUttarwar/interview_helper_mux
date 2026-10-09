// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_refinement_plan_jsonSchema = z.object({
  "run_id": z.string(),
  "schema_version": z.number(),
  "updated_at": z.string().optional(),
  "passes": z.array(z.object({
  "pass_id": z.string(),
  "cfi_id": z.string().optional(),
  "agenda_class": z.string().optional(),
  "decided_at": z.string().optional(),
  "status": z.enum(["activate", "skip"]),
  "gate": z.string().optional(),
  "rationale": z.string().optional(),
  "reason_code": z.string().optional(),
  "input_hash": z.string().optional(),
  "signals": z.record(z.string(), z.unknown()).optional(),
})),
});
