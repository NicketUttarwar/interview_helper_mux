// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_investigation_queue_jsonSchema = z.object({
  "schema_version": z.number().optional(),
  "items": z.array(z.object({
  "id": z.string(),
  "priority": z.enum(["high", "medium", "low"]).optional(),
  "kind": z.string(),
  "question": z.string().optional(),
  "target": z.record(z.string(), z.unknown()).optional(),
  "suggested_action": z.record(z.string(), z.unknown()).optional(),
  "status": z.enum(["open", "in_progress", "done", "wont_fix"]),
  "blocking": z.boolean().optional(),
  "created_by_stage": z.string().optional(),
})),
});
