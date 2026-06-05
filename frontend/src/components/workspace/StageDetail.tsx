import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { stageDescriptionParts } from "../../utils/stageDescription";
import { InfoTooltip } from "../InfoTooltip";
import { HandoffPanel } from "./HandoffPanel";
import { StageOutputsPanel } from "./StageOutputsPanel";
import { TranscriptDockViewer } from "./TranscriptDockViewer";
import type { LlmRoutingAttempt } from "../../types";

export function StageDetail() {
  const { run, config, selectedStage, openActionModal, pendingActionCount } = useApp();
  const [llmAttempts, setLlmAttempts] = useState<LlmRoutingAttempt[]>([]);

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

  const tooltipText = useMemo(() => {
    if (!descParts.summary && !descParts.detail) return "";
    return descParts.detail ? `${descParts.summary} ${descParts.detail}` : descParts.summary;
  }, [descParts]);

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

  if (!selectedStage) {
    return (
      <div className="panel stage-detail">
        <h2>Select a stage</h2>
      </div>
    );
  }

  const statusLabel =
    selectedStage.status === "done"
      ? "Complete"
      : selectedStage.status === "action_required"
        ? "Needs input"
        : selectedStage.status === "locked"
          ? "Locked"
          : "Pending";

  const showHandoff =
    selectedStage.status === "done" && !run?.handoff_ack?.[selectedStage.id];

  return (
    <div className="panel stage-detail">
      <div className="stage-detail-head">
        <h2>
          {selectedStage.title}
          {tooltipText ? <InfoTooltip text={tooltipText} label="About this step" /> : null}
        </h2>
        <span className={`stage-status-pill ${selectedStage.status}`}>{statusLabel}</span>
      </div>

      {selectedStage.status === "action_required" || pendingActionCount > 0 ? (
        <div className="stage-detail-actions">
          <button type="button" className="btn primary sm" onClick={openActionModal}>
            Open checkpoint
            {pendingActionCount > 1 ? ` (${pendingActionCount})` : ""}
          </button>
        </div>
      ) : null}

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

      {showHandoff ? <HandoffPanel /> : null}

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
