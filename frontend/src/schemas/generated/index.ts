// Auto-generated registry — do not edit.
import { z } from "zod";

import { flow_1_master_coverage_audit_jsonSchema } from "./flow_1_master_coverage_audit_jsonSchema";
import { flow_1_master_edl_jsonSchema } from "./flow_1_master_edl_jsonSchema";
import { flow_1_master_edl_narrative_audit_jsonSchema } from "./flow_1_master_edl_narrative_audit_jsonSchema";
import { flow_1_master_narrative_plan_jsonSchema } from "./flow_1_master_narrative_plan_jsonSchema";
import { flow_1_master_podcast_sfx_brief_jsonSchema } from "./flow_1_master_podcast_sfx_brief_jsonSchema";
import { flow_1_master_selection_jsonSchema } from "./flow_1_master_selection_jsonSchema";
import { flow_1_master_transitions_jsonSchema } from "./flow_1_master_transitions_jsonSchema";
import { flow_2_highlights_selection_jsonSchema } from "./flow_2_highlights_selection_jsonSchema";
import { flow_2_highlights_sfx_brief_jsonSchema } from "./flow_2_highlights_sfx_brief_jsonSchema";
import { flow_3_description_show_description_jsonSchema } from "./flow_3_description_show_description_jsonSchema";
import { run_meta_jsonSchema } from "./run_meta_jsonSchema";
import { segments_boundaries_jsonSchema } from "./segments_boundaries_jsonSchema";
import { segments_manifest_jsonSchema } from "./segments_manifest_jsonSchema";
import { segments_nle_edits_jsonSchema } from "./segments_nle_edits_jsonSchema";
import { sound_design_elevenlabs_prompts_jsonSchema } from "./sound_design_elevenlabs_prompts_jsonSchema";
import { sound_design_placement_adjustments_jsonSchema } from "./sound_design_placement_adjustments_jsonSchema";
import { transcript_corrections_jsonSchema } from "./transcript_corrections_jsonSchema";
import { transcript_disfluencies_jsonSchema } from "./transcript_disfluencies_jsonSchema";
import { transcript_review_queue_jsonSchema } from "./transcript_review_queue_jsonSchema";
import { understanding_analysis_state_jsonSchema } from "./understanding_analysis_state_jsonSchema";
import { understanding_content_brief_jsonSchema } from "./understanding_content_brief_jsonSchema";
import { understanding_context_index_jsonSchema } from "./understanding_context_index_jsonSchema";
import { understanding_gap_evaluations_jsonSchema } from "./understanding_gap_evaluations_jsonSchema";
import { understanding_gap_report_jsonSchema } from "./understanding_gap_report_jsonSchema";
import { understanding_investigation_queue_jsonSchema } from "./understanding_investigation_queue_jsonSchema";
import { understanding_sound_design_plan_jsonSchema } from "./understanding_sound_design_plan_jsonSchema";
import { understanding_source_acoustic_profile_jsonSchema } from "./understanding_source_acoustic_profile_jsonSchema";
import { understanding_speakers_jsonSchema } from "./understanding_speakers_jsonSchema";

export const artifactWriteSchemas: Record<string, z.ZodTypeAny> = {
  "flow_1_master/coverage_audit.json": flow_1_master_coverage_audit_jsonSchema,
  "flow_1_master/edl.json": flow_1_master_edl_jsonSchema,
  "flow_1_master/edl_narrative_audit.json": flow_1_master_edl_narrative_audit_jsonSchema,
  "flow_1_master/narrative_plan.json": flow_1_master_narrative_plan_jsonSchema,
  "flow_1_master/podcast_sfx_brief.json": flow_1_master_podcast_sfx_brief_jsonSchema,
  "flow_1_master/selection.json": flow_1_master_selection_jsonSchema,
  "flow_1_master/transitions.json": flow_1_master_transitions_jsonSchema,
  "flow_2_highlights/selection.json": flow_2_highlights_selection_jsonSchema,
  "flow_2_highlights/sfx_brief.json": flow_2_highlights_sfx_brief_jsonSchema,
  "flow_3_description/show_description.json": flow_3_description_show_description_jsonSchema,
  "run_meta.json": run_meta_jsonSchema,
  "segments/boundaries.json": segments_boundaries_jsonSchema,
  "segments/manifest.json": segments_manifest_jsonSchema,
  "segments/nle_edits.json": segments_nle_edits_jsonSchema,
  "sound_design/elevenlabs_prompts.json": sound_design_elevenlabs_prompts_jsonSchema,
  "sound_design/placement_adjustments.json": sound_design_placement_adjustments_jsonSchema,
  "transcript/corrections.json": transcript_corrections_jsonSchema,
  "transcript/disfluencies.json": transcript_disfluencies_jsonSchema,
  "transcript/review_queue.json": transcript_review_queue_jsonSchema,
  "understanding/analysis_state.json": understanding_analysis_state_jsonSchema,
  "understanding/content_brief.json": understanding_content_brief_jsonSchema,
  "understanding/context_index.json": understanding_context_index_jsonSchema,
  "understanding/gap_evaluations.json": understanding_gap_evaluations_jsonSchema,
  "understanding/gap_report.json": understanding_gap_report_jsonSchema,
  "understanding/investigation_queue.json": understanding_investigation_queue_jsonSchema,
  "understanding/sound_design_plan.json": understanding_sound_design_plan_jsonSchema,
  "understanding/source_acoustic_profile.json": understanding_source_acoustic_profile_jsonSchema,
  "understanding/speakers.json": understanding_speakers_jsonSchema,
};
