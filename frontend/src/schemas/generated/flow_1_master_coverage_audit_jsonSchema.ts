// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_1_master_coverage_audit_jsonSchema = z.object({
  "topic_mappings": z.array(z.unknown()),
  "claim_mappings": z.array(z.unknown()).optional(),
  "missing_coverage": z.array(z.unknown()).optional(),
  "orphan_segment_ids": z.array(z.string()).optional(),
  "coverage_score": z.number(),
});
