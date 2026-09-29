// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_post_master_quality_jsonSchema = z.object({
  "version": z.literal(1),
  "generated_at": z.string(),
  "status": z.enum(["pass", "fail", "advisory_fail"]),
  "publish_allowed": z.boolean(),
  "checks": z.array(z.record(z.string(), z.unknown())),
  "failed_checks": z.array(z.string()),
  "never_skipped": z.literal(true),
});
