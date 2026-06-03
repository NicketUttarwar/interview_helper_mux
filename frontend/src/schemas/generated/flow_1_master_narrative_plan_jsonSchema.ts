// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const flow_1_master_narrative_plan_jsonSchema = z.object({
  "arc_summary": z.string().min(1),
  "chapters": z.array(z.object({
  "chapter_id": z.string(),
  "title": z.string(),
  "topic_tags": z.array(z.unknown()).optional(),
  "suggested_open_segment_id": z.string(),
})),
  "ordering_constraints": z.array(z.unknown()),
  "pacing_notes": z.string().optional(),
});
