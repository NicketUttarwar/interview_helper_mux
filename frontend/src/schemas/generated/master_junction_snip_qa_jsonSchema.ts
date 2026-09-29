// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_junction_snip_qa_jsonSchema = z.object({
  "version": z.literal(1),
  "mode": z.string().optional(),
  "skipped": z.boolean().optional(),
  "reason": z.string().optional(),
  "pace_class": z.string().optional(),
  "findings": z.array(z.record(z.string(), z.unknown())).optional(),
  "applied": z.array(z.record(z.string(), z.unknown())).optional(),
  "remaster_rounds": z.number().optional(),
  "llm_calls": z.number().optional(),
  "advisory": z.boolean().optional(),
  "blocking": z.boolean().optional(),
  "generated_at": z.string(),
});
