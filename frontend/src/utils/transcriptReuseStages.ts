/** Only the initial transcribe reuse opens the one-time edit interstitial. */
export const TRANSCRIPT_REUSE_EDIT_STAGES = new Set(["transcribe"]);

export function isTranscriptReuseEditStage(stageId: string): boolean {
  return TRANSCRIPT_REUSE_EDIT_STAGES.has(stageId);
}
