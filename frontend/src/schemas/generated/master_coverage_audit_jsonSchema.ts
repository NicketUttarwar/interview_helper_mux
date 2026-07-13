// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_coverage_audit_jsonSchema = z.object({
  "topic_mappings": z.array(z.object({
  "topic": z.string(),
  "segment_ids": z.array(z.string()),
  "covered": z.boolean(),
})),
  "claim_mappings": z.array(z.object({
  "claim": z.string(),
  "segment_ids": z.array(z.string()),
  "covered": z.boolean(),
})).optional(),
  "missing_coverage": z.array(z.object({
  "item": z.string(),
  "suggestion": z.string(),
})).optional(),
  "orphan_segment_ids": z.array(z.string()).optional(),
  "coverage_score": z.number(),
});
