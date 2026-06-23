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
import { stageAwaitingWriteApproval } from "../../utils/writeApproval";
import type { LlmRoutingAttempt } from "../../types";
import { useStageProgress } from "../../hooks/useStageProgress";
import { stageNeedsPendingAction } from "../../utils/pendingAction";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";
import { PreviewListenPromo } from "../guidance/PreviewListenPromo";
import { StepActionHeader } from "./StepActionHeader";
import { useStageOperatorAction } from "../../hooks/useOperatorAction";
import {
  executeBodyForStage,
  invokeOperatorActionPrimary,
  invokeOperatorActionSecondary,
} from "../../utils/operatorActionHandlers";

export function StageDetail() {
  const {
    run,
    config,
    selectedStage,
    selectedStageId,
    jobRunning,
    apiGrants,
    actionBusy,
    selectStage,
    redoFromStage,
    appendClientLog,
    setPipelineSubTab,
    executeJob,
    runNextStage,
    setActivityLogTab,
    setActivityLogCollapsed,
    setActiveSubstepId,
    expandStage,
    skipOptionalStage,
  } = useApp();
  const [llmAttempts, setLlmAttempts] = useState<LlmRoutingAttempt[]>([]);
  const { fullyComplete } = useStageProgress(selectedStageId);

  const layoutStageId = selectedStage?.id ?? selectedStageId;
  const layoutStageStatus = selectedStage?.status;

  const handoffPaths = useMemo(() => {
    if (!selectedStage || !run) return [];
    return getHandoffPathsLocal(selectedStage, run.log_tail);
  }, [selectedStage, run?.log_tail]);

  const showHandoff = useMemo(() => {
    if (!selectedStage || !run) return false;
    return (
      layoutStageStatus === "done" &&
      handoffPaths.length > 0 &&
      !run.handoff_ack?.[selectedStage.id]
    );
  }, [selectedStage, run, layoutStageStatus, handoffPaths.length]);

  const showDoneShell = useMemo(() => {
    if (!run || !layoutStageId) return false;
    return (
      fullyComplete &&
      !showHandoff &&
      !stageNeedsPendingAction(run, layoutStageId, apiGrants)
    );
  }, [fullyComplete, showHandoff, run, layoutStageId, apiGrants]);

  const nav = useMemo(
    () =>
      resolvePipelineNav(run, {
        selectedStageId,
        jobRunning,
        apiGrants,
      }),
    [run, selectedStageId, jobRunning, apiGrants, config],
  );

  const stageAction = useStageOperatorAction(run, selectedStageId, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });

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
    const targetId = nav.currentStage?.id || nav.nextStage?.id;
    if (targetId) void selectStage(targetId);
  }, [run, selectedStageId, nav.currentStage?.id, nav.nextStage?.id, selectStage]);

  if (!selectedStage || !stageAction) {
    return (
      <div className="panel stage-detail">
        <h2>Loading step…</h2>
      </div>
    );
  }

  const stepEntry = nav.numberedStages.find((n) => n.stage.id === selectedStage.id);

  const writePendingOnly =
    stageAwaitingWriteApproval(run, selectedStage.id) &&
    selectedStage.status !== "action_required" &&
    !showHandoff;

  const needsGateCheckpoint =
    !writePendingOnly &&
    !fullyComplete &&
    (selectedStage.status === "action_required" ||
      showHandoff ||
      (run?.job?.status === "gate" && run.job.stage === selectedStage.id));

  const handlePrimary = () => {
    invokeOperatorActionPrimary(stageAction, {
      openModal: (sid, subId) => {
        if (sid) {
          void selectStage(sid);
          expandStage(sid);
        }
        if (subId) setActiveSubstepId(subId);
      },
      runStage: (sid) => void executeJob(executeBodyForStage(sid)),
      continueNext: () => void runNextStage(),
      viewLogs: () => {
        setActivityLogTab("live");
        setActivityLogCollapsed(false);
      },
    });
  };

  const handleSecondary = () => {
    invokeOperatorActionSecondary(stageAction, {
      viewLogs: () => {
        setActivityLogTab("live");
        setActivityLogCollapsed(false);
      },
      skipOptional: (sid) => void skipOptionalStage(sid),
    });
  };

  return (
    <div className={`panel stage-detail${showDoneShell ? " stage-detail--done" : ""}`}>
      <StepActionHeader
        action={stageAction}
        stepNumber={stepEntry?.number}
        onPrimary={handlePrimary}
        onSecondary={
          stageAction.secondaryLabel ? handleSecondary : undefined
        }
        busy={actionBusy}
      />

      <details className="stage-about-details">
        <summary className="stage-about-summary">
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
        </summary>
        {descParts.summary ? (
          <p className="hint stage-detail-summary">{descParts.summary}</p>
        ) : null}
        {stepEntry ? (
          <p className="hint sm">{stepEntry.phaseLabel} phase</p>
        ) : null}
      </details>

      {showDoneShell && stageAction.mode !== "done" ? (
        <div className="stage-detail-done-shell">
          <StepDoneBanner variant="step" />
          <StageOutputsPanel stage={selectedStage} />
          {!jobRunning ? (
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
        </div>
      ) : (
        <>
          <StageGuidancePanel stage={selectedStage} />

          {selectedStage.id === "assembly_preview" ? <PreviewListenPromo /> : null}

          <StageActivityStrip />

          {!writePendingOnly ? <StageReuseSection stage={selectedStage} /> : null}
          <WriteApprovalPanel stage={selectedStage} />

          {needsGateCheckpoint ? (
            <div className="stage-detail-checkpoint panel-inset" id="stage-gate-panel">
              <h3 className="stage-outputs-title">Your action</h3>
              <GateActions stage={selectedStage} />
              {showHandoff ? <HandoffPanel /> : null}
            </div>
          ) : selectedStage.status === "action_required" ||
            (run?.job?.status === "gate" && run.job.stage === selectedStage.id) ? (
            <GateActions stage={selectedStage} />
          ) : null}

          {showHandoff && !needsGateCheckpoint ? (
            <div className="stage-detail-checkpoint panel-inset" id="stage-handoff-panel">
              <HandoffPanel />
            </div>
          ) : null}

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
        </>
      )}

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
