// Auto-generated registry — do not edit.
import type { z } from "zod";

const schemaLoaders: Record<string, () => Promise<z.ZodTypeAny>> = {
  "flow_1_master/coverage_audit.json": async () =>
    (await import("./flow_1_master_coverage_audit_jsonSchema")).flow_1_master_coverage_audit_jsonSchema,
  "flow_1_master/edl.json": async () =>
    (await import("./flow_1_master_edl_jsonSchema")).flow_1_master_edl_jsonSchema,
  "flow_1_master/edl_narrative_audit.json": async () =>
    (await import("./flow_1_master_edl_narrative_audit_jsonSchema")).flow_1_master_edl_narrative_audit_jsonSchema,
  "flow_1_master/narrative_plan.json": async () =>
    (await import("./flow_1_master_narrative_plan_jsonSchema")).flow_1_master_narrative_plan_jsonSchema,
  "flow_1_master/podcast_sfx_brief.json": async () =>
    (await import("./flow_1_master_podcast_sfx_brief_jsonSchema")).flow_1_master_podcast_sfx_brief_jsonSchema,
  "flow_1_master/selection.json": async () =>
    (await import("./flow_1_master_selection_jsonSchema")).flow_1_master_selection_jsonSchema,
  "flow_1_master/transitions.json": async () =>
    (await import("./flow_1_master_transitions_jsonSchema")).flow_1_master_transitions_jsonSchema,
  "flow_2_highlights/selection.json": async () =>
    (await import("./flow_2_highlights_selection_jsonSchema")).flow_2_highlights_selection_jsonSchema,
  "flow_2_highlights/sfx_brief.json": async () =>
    (await import("./flow_2_highlights_sfx_brief_jsonSchema")).flow_2_highlights_sfx_brief_jsonSchema,
  "flow_3_description/show_description.json": async () =>
    (await import("./flow_3_description_show_description_jsonSchema")).flow_3_description_show_description_jsonSchema,
  "run_meta.json": async () =>
    (await import("./run_meta_jsonSchema")).run_meta_jsonSchema,
  "segments/boundaries.json": async () =>
    (await import("./segments_boundaries_jsonSchema")).segments_boundaries_jsonSchema,
  "segments/manifest.json": async () =>
    (await import("./segments_manifest_jsonSchema")).segments_manifest_jsonSchema,
  "segments/nle_edits.json": async () =>
    (await import("./segments_nle_edits_jsonSchema")).segments_nle_edits_jsonSchema,
  "sound_design/mmaudio_qa.json": async () =>
    (await import("./sound_design_mmaudio_qa_jsonSchema")).sound_design_mmaudio_qa_jsonSchema,
  "sound_design/placement_adjustments.json": async () =>
    (await import("./sound_design_placement_adjustments_jsonSchema")).sound_design_placement_adjustments_jsonSchema,
  "sound_design/sfx_prompts.json": async () =>
    (await import("./sound_design_sfx_prompts_jsonSchema")).sound_design_sfx_prompts_jsonSchema,
  "transcript/corrections.json": async () =>
    (await import("./transcript_corrections_jsonSchema")).transcript_corrections_jsonSchema,
  "transcript/disfluencies.json": async () =>
    (await import("./transcript_disfluencies_jsonSchema")).transcript_disfluencies_jsonSchema,
  "transcript/review_queue.json": async () =>
    (await import("./transcript_review_queue_jsonSchema")).transcript_review_queue_jsonSchema,
  "understanding/analysis_state.json": async () =>
    (await import("./understanding_analysis_state_jsonSchema")).understanding_analysis_state_jsonSchema,
  "understanding/coherence_report.json": async () =>
    (await import("./understanding_coherence_report_jsonSchema")).understanding_coherence_report_jsonSchema,
  "understanding/content_brief.json": async () =>
    (await import("./understanding_content_brief_jsonSchema")).understanding_content_brief_jsonSchema,
  "understanding/context_index.json": async () =>
    (await import("./understanding_context_index_jsonSchema")).understanding_context_index_jsonSchema,
  "understanding/gap_evaluations.json": async () =>
    (await import("./understanding_gap_evaluations_jsonSchema")).understanding_gap_evaluations_jsonSchema,
  "understanding/gap_report.json": async () =>
    (await import("./understanding_gap_report_jsonSchema")).understanding_gap_report_jsonSchema,
  "understanding/interview_spine.json": async () =>
    (await import("./understanding_interview_spine_jsonSchema")).understanding_interview_spine_jsonSchema,
  "understanding/investigation_queue.json": async () =>
    (await import("./understanding_investigation_queue_jsonSchema")).understanding_investigation_queue_jsonSchema,
  "understanding/sonic_context.json": async () =>
    (await import("./understanding_sonic_context_jsonSchema")).understanding_sonic_context_jsonSchema,
  "understanding/sound_design_plan.json": async () =>
    (await import("./understanding_sound_design_plan_jsonSchema")).understanding_sound_design_plan_jsonSchema,
  "understanding/source_acoustic_profile.json": async () =>
    (await import("./understanding_source_acoustic_profile_jsonSchema")).understanding_source_acoustic_profile_jsonSchema,
  "understanding/speakers.json": async () =>
    (await import("./understanding_speakers_jsonSchema")).understanding_speakers_jsonSchema,
};

const schemaCache = new Map<string, z.ZodTypeAny>();

export const artifactWriteSchemaPaths = Object.keys(schemaLoaders);

export async function loadArtifactWriteSchema(
  path: string,
): Promise<z.ZodTypeAny | null> {
  const loader = schemaLoaders[path];
  if (!loader) return null;
  const cached = schemaCache.get(path);
  if (cached) return cached;
  const schema = await loader();
  schemaCache.set(path, schema);
  return schema;
}

/** Fire-and-forget warm-up for editor UX */
export function prefetchArtifactWriteSchema(path: string): void {
  void loadArtifactWriteSchema(path);
}
