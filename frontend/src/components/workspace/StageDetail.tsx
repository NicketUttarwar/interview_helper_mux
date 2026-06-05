import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { GateActions } from "../gates/GateActions";
import { HandoffPanel } from "./HandoffPanel";
import { StageOutputsPanel } from "./StageOutputsPanel";
import { TranscriptDockViewer } from "./TranscriptDockViewer";
import { InfoTooltip } from "../InfoTooltip";
import { stageDescriptionParts } from "../../utils/stageDescription";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { getHandoffPathsLocal } from "../../utils/checkpoint";
import type { LlmRoutingAttempt } from "../../types";

export function StageDetail() {
  const {
    run,
    config,
    selectedStage,
    selectedStageId,
    openActionModal,
    jobRunning,
    apiGrants,
    selectStage,
  } = useApp();
  const [llmAttempts, setLlmAttempts] = useState<LlmRoutingAttempt[]>([]);

  const nav = useMemo(
    () =>
      resolvePipelineNav(run, {
        selectedStageId,
        jobRunning,
        apiGrants,
        pauseSecondsDefault: config?.journey_ui?.step_through_pause_seconds ?? 10,
      }),
    [run, selectedStageId, jobRunning, apiGrants, config],
  );

  const llmStageIds = useMemo(
    () => new Set(config?.llm_routing_stage_ids || []),
    [config?.llm_routing_stage_ids],
  );

  const descParts = useMemo(
    () =>
      selectedStage
        ? stageDescriptionParts(selectedStage.description)
        : { summary: "", detail: null },
    [selectedStage],
  );

  useEffect(() => {
    if (!run || !selectedStage || !llmStageIds.has(selectedStage.id)) {
      setLlmAttempts([]);
      return;
    }
    void api<{ attempts: LlmRoutingAttempt[] }>(`/api/runs/${run.run_id}/llm-routing`)
      .then((data) => {
        setLlmAttempts((data.attempts || []).filter((a) => a.stage === selectedStage.id));
      })
      .catch(() => setLlmAttempts([]));
  }, [run, selectedStage, llmStageIds]);

  useEffect(() => {
    if (!run || selectedStageId) return;
    const target = nav.currentStage || nav.nextStage;
    if (target) void selectStage(target.id);
  }, [run, selectedStageId, nav.currentStage, nav.nextStage, selectStage]);

  if (!selectedStage) {
    return (
      <div className="panel stage-detail">
        <h2>Loading step…</h2>
      </div>
    );
  }

  const stepEntry = nav.numberedStages.find((n) => n.stage.id === selectedStage.id);
  const statusLabel =
    selectedStage.status === "done"
      ? "Complete"
      : selectedStage.status === "action_required"
        ? "Needs your input"
        : selectedStage.status === "locked"
          ? "Locked"
          : "Ready to run";

  const handoffPaths = getHandoffPathsLocal(selectedStage, run?.log_tail);
  const showHandoff =
    selectedStage.status === "done" &&
    handoffPaths.length > 0 &&
    !run?.handoff_ack?.[selectedStage.id];

  const needsCheckpoint =
    selectedStage.status === "action_required" ||
    showHandoff ||
    (run?.job?.status === "gate" && run.job.stage === selectedStage.id);

  return (
    <div className="panel stage-detail">
      <div className="stage-detail-head">
        <div>
          {stepEntry ? (
            <p className="stage-detail-step-num">Step {stepEntry.number}</p>
          ) : null}
          <h2>
            {selectedStage.title}
            {descParts.summary ? (
              <InfoTooltip
                text={
                  descParts.detail
                    ? `${descParts.summary} ${descParts.detail}`
                    : descParts.summary
                }
                label="About this step"
              />
            ) : null}
          </h2>
          {descParts.summary ? <p className="hint stage-detail-summary">{descParts.summary}</p> : null}
        </div>
        <span className={`stage-status-pill ${selectedStage.status}`}>{statusLabel}</span>
      </div>

      {needsCheckpoint ? (
        <div className="stage-detail-checkpoint panel-inset">
          <h3 className="stage-outputs-title">Your action</h3>
          <GateActions stage={selectedStage} />
          {showHandoff ? <HandoffPanel /> : null}
          {selectedStage.status === "action_required" ? null : showHandoff ? (
            <div className="stage-detail-actions">
              <button type="button" className="btn primary sm" onClick={openActionModal}>
                Review in full-screen panel
              </button>
            </div>
          ) : null}
        </div>
      ) : (
        <GateActions stage={selectedStage} />
      )}

      <StageOutputsPanel stage={selectedStage} />

      {(selectedStage.id === "transcribe" ||
        selectedStage.id === "transcript_review" ||
        selectedStage.id === "transcript_review_build") &&
      selectedStage.artifacts_present?.includes("transcript/full.json") ? (
        <section className="stage-transcript-dock">
          <h3 className="stage-outputs-title">
            Transcript
            <InfoTooltip text="Click words to seek audio. Double-click to edit." />
          </h3>
          <TranscriptDockViewer />
        </section>
      ) : null}

      {llmAttempts.length > 0 ? (
        <div className="llm-routing-panel">
          <h3 className="stage-outputs-title">LLM routing</h3>
          <ul className="llm-routing-list">
            {llmAttempts.map((r, i) => (
              <li key={i}>
                <span className="llm-routing-task">
                  {r.task_kind || "primary"}
                  {r.attempt ? ` #${r.attempt}` : ""}
                </span>
                <span className={`llm-routing-verdict verdict-${r.verdict || "unknown"}`}>
                  {r.verdict || "—"}
                </span>
                <span className="muted">
                  {r.model_tier ? `${r.model_tier}` : ""}
                  {r.shard_count != null ? ` · shards ${r.shard_count}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
