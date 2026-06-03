// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_gap_report_jsonSchema = z.object({
  "interviewer_lines": z.array(z.object({
  "line_id": z.string().optional(),
  "gap_type": z.string(),
  "text": z.string(),
  "targets_segment_id": z.string(),
  "placement": z.enum(["before", "after"]),
  "delivery": z.enum(["record", "synthesize"]),
  "rationale": z.string().optional(),
})),
});
