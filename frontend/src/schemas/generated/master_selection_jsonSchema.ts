// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_selection_jsonSchema = z.object({
  "ordered_segment_ids": z.array(z.string()).min(1),
  "chapters": z.array(z.object({
  "title": z.string(),
  "segment_ids": z.array(z.string()),
})).optional(),
  "excluded_segment_ids": z.array(z.object({
  "segment_id": z.string(),
  "reason": z.string(),
})).optional(),
  "notes": z.string().optional(),
  "order_content_hash": z.string().optional(),
  "order_lock": z.object({
  "version": z.number().optional(),
  "revision": z.number().optional(),
  "authority": z.string().optional(),
  "ordered_segment_ids": z.array(z.string()).optional(),
  "order_content_hash": z.string().optional(),
  "created_by": z.string().optional(),
  "supersedes": z.string().nullable().optional(),
}).optional(),
  "order_authority": z.string().optional(),
  "optimizer_candidate_id": z.string().optional(),
  "optimizer_score": z.unknown().optional(),
});
