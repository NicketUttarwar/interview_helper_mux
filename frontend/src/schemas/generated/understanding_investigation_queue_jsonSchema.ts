// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_investigation_queue_jsonSchema = z.object({
  "schema_version": z.number().optional(),
  "items": z.array(z.object({
  "id": z.string(),
  "priority": z.enum(["high", "medium", "low"]).optional(),
  "kind": z.string(),
  "question": z.string().optional(),
  "target": z.object({
  "segment_id": z.string().optional(),
  "field": z.string().optional(),
  "stage": z.string().optional(),
  "window_id": z.string().optional(),
  "start_ms": z.number().optional(),
  "end_ms": z.number().optional(),
  "theme_id": z.string().optional(),
  "claim_id": z.string().optional(),
  "risk_id": z.string().optional(),
}).optional(),
  "evidence": z.object({
  "novelty_score": z.number().optional(),
  "theme_alignment": z.number().optional(),
  "drift_score": z.number().optional(),
}).optional(),
  "suggested_action": z.record(z.string(), z.unknown()).optional(),
  "status": z.enum(["open", "in_progress", "done", "wont_fix"]),
  "blocking": z.boolean().optional(),
  "created_by_stage": z.string().optional(),
})),
});
