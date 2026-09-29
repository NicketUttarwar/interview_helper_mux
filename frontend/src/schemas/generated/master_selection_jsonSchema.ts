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
  "admitted_story_segment_ids": z.array(z.string()).optional(),
  "considerable_segment_ids": z.array(z.string()).optional(),
  "media_ip_cta": z.array(z.object({
  "segment_id": z.string(),
  "clearly_media_ip_pitch": z.boolean(),
  "mixed_with_story": z.boolean().optional(),
  "must_keep_in_clip": z.boolean().optional(),
  "cta_region": z.enum(["whole", "start", "end", "middle"]).optional(),
  "cut_ms": z.array(z.number()).optional(),
  "cta_open": z.boolean().optional(),
  "open_choice": z.enum(["story_child_first", "third_person_opener"]).optional(),
})).optional(),
});
