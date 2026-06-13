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
import { StageGuidancePanel } from "../guidance/StageGuidancePanel";
import { StageActivityStrip } from "../activity/StageActivityStrip";
import { StageReuseSection } from "../guidance/StageReuseSection";
import { WriteApprovalPanel } from "../guidance/WriteApprovalPanel";
import { stageNeedsPendingAction } from "../../utils/pendingAction";
import type { LlmRoutingAttempt } from "../../types";

export function StageDetail() {
  const {
    run,
    config,
    selectedStage,
    selectedStageId,
    actionModalOpen,
    jobRunning,
    apiGrants,
    selectStage,
    redoFromStage,
    appendClientLog,
    setPipelineSubTab,
  } = useApp();
  const [llmAttempts, setLlmAttempts] = useState<LlmRoutingAttempt[]>([]);

  const nav = useMemo(
    () =>
      resolvePipelineNav(run, {
        selectedStageId,
        jobRunning,
        apiGrants,
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
      .catch((e) => {
        setLlmAttempts([]);
        appendClientLog(
          e instanceof Error ? e.message : "Failed to load LLM routing summary",
          "warning",
        );
      });
  }, [run, selectedStage, llmStageIds, appendClientLog]);

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
  const isRunningThisStage =
    jobRunning &&
    (run?.job?.current_stage === selectedStage.id ||
      run?.job?.stage === selectedStage.id);
  const statusLabel =
    isRunningThisStage
      ? "Running"
      : selectedStage.status === "awaiting_write_approval"
        ? "Review before saving"
      : selectedStage.status === "done"
        ? "Done"
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
    selectedStage.status === "awaiting_write_approval" ||
    showHandoff ||
    (run?.job?.status === "gate" && run.job.stage === selectedStage.id) ||
    stageNeedsPendingAction(run, selectedStage.id, apiGrants);

  return (
    <div className="panel stage-detail">
      <div className="stage-detail-head">
        <div>
          {stepEntry ? (
            <p className="stage-detail-step-num">
              Pipeline step {stepEntry.number} · {stepEntry.phaseLabel} phase
            </p>
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

      <StageGuidancePanel stage={selectedStage} />

      <StageActivityStrip />

      {!actionModalOpen ? <StageReuseSection stage={selectedStage} /> : null}
      {!actionModalOpen ? <WriteApprovalPanel stage={selectedStage} /> : null}

      {needsCheckpoint ? (
        <div className="stage-detail-checkpoint panel-inset">
          <h3 className="stage-outputs-title">Your action</h3>
          <GateActions stage={selectedStage} />
          {showHandoff ? <HandoffPanel /> : null}
        </div>
      ) : (
        <GateActions stage={selectedStage} />
      )}

      <StageOutputsPanel stage={selectedStage} />

      {selectedStage.status === "done" && !jobRunning ? (
        <div className="stage-detail-actions">
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => void redoFromStage()}
            title="Clear this step and later markers, then re-run from here"
          >
            Redo from this step
          </button>
        </div>
      ) : null}

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
          <div className="stage-outputs-title-row">
            <h3 className="stage-outputs-title">LLM routing</h3>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => setPipelineSubTab("llm_calls")}
            >
              Open full debug
            </button>
          </div>
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
                  {r.primary_attempt_count != null && r.budget_remaining_primary != null
                    ? ` · budget ${r.primary_attempt_count}/${r.primary_attempt_count + r.budget_remaining_primary}`
                    : ""}
                  {(r.stuck_count ?? 0) > 0 ? ` · stuck ${r.stuck_count}` : ""}
                </span>
                {r.deterministic_lint_errors?.length ? (
                  <span className="lint-error-chip" title={r.deterministic_lint_errors.join("; ")}>
                    lint: {r.deterministic_lint_errors[0].slice(0, 48)}
                    {r.deterministic_lint_errors[0].length > 48 ? "…" : ""}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
