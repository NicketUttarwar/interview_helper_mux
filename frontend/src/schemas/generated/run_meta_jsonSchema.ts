// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py
import { z } from "zod";

export const run_meta_jsonSchema = z.object({
  "execution_id": z.string().optional(),
  "execution_number": z.unknown().optional(),
  "input_audio_path": z.string().optional(),
  "source_audio_hash": z.string().optional(),
  "source_audio_hash_short": z.string().optional(),
  "storage_root": z.string().optional(),
  "stage_reuse": z.record(z.string(), z.unknown()).optional(),
  "pending_write_approval": z.record(z.string(), z.unknown()).optional(),
  "created_at": z.string().optional(),
  "updated_at": z.string().optional(),
  "selected_flow": z.enum(["flow1", "flow2", "flow3"]).optional(),
  "selected_at": z.string().optional(),
  "flow_intent": z.enum(["flow1", "flow2", "flow3"]).optional(),
  "flow_intent_at": z.string().optional(),
  "operator_phase": z.enum(["prepare", "understand", "complete", "create", "polish", "ship"]).optional(),
  "operator_phase_updated_at": z.string().optional(),
  "journey_milestones": z.record(z.string(), z.unknown()).optional(),
  "preview_listened_at": z.string().optional(),
  "audio_preclean": z.record(z.string(), z.unknown()).optional(),
  "elevenlabs_prompt_review": z.record(z.string(), z.unknown()).optional(),
  "elevenlabs_listen_results": z.array(z.unknown()).optional(),
  "qc_summaries": z.record(z.string(), z.unknown()).optional(),
});
