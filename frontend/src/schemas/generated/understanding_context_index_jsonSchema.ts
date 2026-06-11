// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const understanding_context_index_jsonSchema = z.object({
  "schema_version": z.number(),
  "run_id": z.string(),
  "stage_plans": z.record(z.string(), z.unknown()),
  "padding_rules": z.object({
  "max_user_json_chars": z.number().optional(),
  "max_volley_middle_chars_full": z.number().optional(),
  "max_volley_middle_chars_shard": z.number().optional(),
  "max_entries_per_kind": z.record(z.string(), z.unknown()).optional(),
}),
  "artifacts_registry": z.record(z.string(), z.unknown()).optional(),
  "volley_entries": z.array(z.unknown()),
  "meta": z.object({
  "plans_synced_at": z.string().optional(),
  "entries_count": z.number().optional(),
  "last_updated_at": z.string().optional(),
}).optional(),
});
