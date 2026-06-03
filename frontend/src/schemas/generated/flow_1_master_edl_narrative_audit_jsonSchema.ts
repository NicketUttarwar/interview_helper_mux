// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_1_master_edl_narrative_audit_jsonSchema = z.object({
  "verdict": z.enum(["pass", "warn", "fail"]),
  "blocking_issues": z.array(z.object({
  "issue": z.string(),
  "evidence": z.array(z.string()),
  "recommended_action": z.string(),
})),
  "warnings": z.array(z.unknown()),
  "recommended_actions": z.array(z.string()),
  "reasoning_summary": z.string(),
});
