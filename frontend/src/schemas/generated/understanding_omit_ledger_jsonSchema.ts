// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_omit_ledger_jsonSchema = z.object({
  "version": z.number(),
  "order_content_hash": z.string().nullable().optional(),
  "order_lock": z.record(z.string(), z.unknown()).nullable().optional(),
  "entries": z.array(z.object({
  "entry_id": z.string(),
  "kind": z.enum(["segment_exclude", "layup_skip", "nugget_waive", "gap_line_skip", "suppress", "defer", "structural_omit", "asset_adjust"]),
  "subject_id": z.string(),
  "target_segment_id": z.string().nullable().optional(),
  "decision": z.enum(["omit", "defer", "suppress", "waive"]),
  "reason_code": z.string(),
  "rationale": z.string().nullable().optional(),
  "evidence_refs": z.array(z.string()).optional(),
  "value_forgone": z.array(z.string()).optional(),
  "compensating_path": z.string().nullable().optional(),
  "revisit_if": z.array(z.string()).optional(),
  "decision_confidence": z.number().nullable().optional(),
  "owner_stage": z.string(),
  "source_artifact": z.string().nullable().optional(),
  "replacement_ref": z.string().nullable().optional(),
  "active": z.boolean(),
  "superseded_by": z.string().nullable().optional(),
  "operator_override": z.boolean().optional(),
  "decided_at": z.string().nullable().optional(),
  "provenance": z.record(z.string(), z.unknown()).nullable().optional(),
})),
  "summary": z.object({
  "active_count": z.number().optional(),
  "by_kind": z.record(z.string(), z.unknown()).optional(),
  "unresolved_high_salience": z.number().optional(),
  "compensated_count": z.number().optional(),
}),
  "_meta": z.record(z.string(), z.unknown()).optional(),
});
