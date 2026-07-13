// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const master_narrative_plan_jsonSchema = z.object({
  "arc_summary": z.string().min(1),
  "chapters": z.array(z.object({
  "chapter_id": z.string(),
  "title": z.string(),
  "topic_tags": z.array(z.string()).optional(),
  "suggested_open_segment_id": z.string(),
  "act_number": z.number().optional(),
  "act_title": z.string().optional(),
  "tension_level": z.number().optional(),
  "is_moat_chapter": z.boolean().optional(),
})).max(12),
  "strategic_moat_concept": z.string().nullable().optional(),
  "five_act_coverage": z.object({
  "act_1": z.number().optional(),
  "act_2": z.number().optional(),
  "act_3": z.number().optional(),
  "act_4": z.number().optional(),
  "act_5": z.number().optional(),
}).optional(),
  "ordering_constraints": z.array(z.object({
  "before_segment_id": z.string(),
  "after_segment_id": z.string(),
  "reason": z.string(),
})),
  "pacing_notes": z.string().optional(),
});
