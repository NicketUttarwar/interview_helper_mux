// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_1_master_narrative_plan_jsonSchema = z.object({
  "arc_summary": z.string().min(1),
  "chapters": z.array(z.object({
  "chapter_id": z.string(),
  "title": z.string(),
  "topic_tags": z.array(z.string()).optional(),
  "suggested_open_segment_id": z.string(),
})).max(12),
  "ordering_constraints": z.array(z.object({
  "before_segment_id": z.string(),
  "after_segment_id": z.string(),
  "reason": z.string(),
})),
  "pacing_notes": z.string().optional(),
});
