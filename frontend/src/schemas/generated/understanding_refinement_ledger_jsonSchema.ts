// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_refinement_ledger_jsonSchema = z.object({
  "run_id": z.string(),
  "schema_version": z.number(),
  "calls": z.array(z.object({
  "seq": z.number(),
  "at": z.string().optional(),
  "cfi_id": z.string(),
  "human_key": z.string().optional(),
  "stage_id": z.string(),
  "pass_id": z.string().nullable().optional(),
  "pass_index": z.number().optional(),
  "kind": z.string(),
  "outcome": z.string().optional(),
  "refines_cfi": z.string().optional(),
  "gate": z.string().optional(),
  "input_hash": z.string().optional(),
  "detail": z.record(z.string(), z.unknown()).optional(),
})),
  "counts_by_cfi": z.record(z.string(), z.unknown()),
  "order_of_refinement_pass_ids": z.array(z.string()),
});
