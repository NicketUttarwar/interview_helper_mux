// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_junction_thought_complete_jsonSchema = z.object({
  "version": z.literal(1),
  "generated_at": z.string(),
  "cuts": z.array(z.object({
  "case_id": z.string().min(1),
  "keep_end_ms": z.number(),
  "remainder_start_ms": z.number().nullable().optional(),
  "consumed_segment_ids": z.array(z.string()).optional(),
  "rationale": z.string().optional(),
  "confidence": z.number().optional(),
})),
  "llm_calls": z.number().optional(),
  "source": z.string().optional(),
  "error": z.string().nullable().optional(),
});
