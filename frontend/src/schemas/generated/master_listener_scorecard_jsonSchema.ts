// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_listener_scorecard_jsonSchema = z.object({
  "version": z.literal(1),
  "generated_at": z.string(),
  "overall": z.number(),
  "dimensions": z.record(z.string(), z.unknown()),
  "quality_status": z.enum(["pass", "fail", "advisory_fail"]),
  "publish_allowed": z.boolean(),
});
