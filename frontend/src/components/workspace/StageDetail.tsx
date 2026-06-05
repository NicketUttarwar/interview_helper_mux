import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { stageDescriptionParts } from "../../utils/stageDescription";
import { HandoffPanel } from "./HandoffPanel";
import { StageOutputsPanel } from "./StageOutputsPanel";
import type { LlmRoutingAttempt } from "../../types";

export function StageDetail() {
  const { run, config, selectedStage, openActionModal, pendingActionCount } =
    useApp();
  const [llmAttempts, setLlmAttempts] = useState<LlmRoutingAttempt[]>([]);
  const [showFullDescription, setShowFullDescription] = useState(false);

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
    setShowFullDescription(false);
  }, [selectedStage?.id]);

  useEffect(() => {
    if (!run || !selectedStage || !llmStageIds.has(selectedStage.id)) {
      setLlmAttempts([]);
      return;
    }
    void api<{ attempts: LlmRoutingAttempt[] }>(
      `/api/runs/${run.run_id}/llm-routing`,
    )
      .then((data) => {
        setLlmAttempts(
          (data.attempts || []).filter((a) => a.stage === selectedStage.id),
        );
      })
      .catch(() => setLlmAttempts([]));
  }, [run, selectedStage, llmStageIds]);

  if (!selectedStage) {
    return (
      <div className="panel stage-detail">
        <h2>Select a stage</h2>
        <p className="hint">Choose a step in the sidebar — use the command bar for what to do next.</p>
      </div>
    );
  }

  const statusLabel =
    selectedStage.status === "done"
      ? "Complete"
      : selectedStage.status === "action_required"
        ? "Needs your input"
        : selectedStage.status === "locked"
          ? "Locked"
          : "Pending";

  const showHandoff =
    selectedStage.status === "done" && !run?.handoff_ack?.[selectedStage.id];

  return (
    <div className="panel stage-detail">
      <div className="stage-detail-head">
        <h2>{selectedStage.title}</h2>
        <span className={`stage-status-pill ${selectedStage.status}`}>{statusLabel}</span>
        <span className="stage-id-hint muted">{selectedStage.id}</span>
      </div>

      <p className="lead">{descParts.summary}</p>
      {descParts.detail ? (
        <>
          {showFullDescription ? (
            <p className="hint stage-description-detail">{descParts.detail}</p>
          ) : null}
          <button
            type="button"
            className="btn ghost sm stage-description-toggle"
            onClick={() => setShowFullDescription((v) => !v)}
          >
            {showFullDescription ? "Less detail" : "More about this step"}
          </button>
        </>
      ) : null}

      {selectedStage.status === "action_required" || pendingActionCount > 0 ? (
        <div className="stage-detail-actions">
          <button type="button" className="btn primary sm" onClick={openActionModal}>
            Open checkpoint
            {pendingActionCount > 1 ? ` (${pendingActionCount})` : ""}
          </button>
        </div>
      ) : null}

      <StageOutputsPanel stage={selectedStage} />

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
                  {r.shard_plan_source ? ` · plan ${r.shard_plan_source}` : ""}
                  {(r.truncation_flags || []).length
                    ? ` · trunc ${(r.truncation_flags || []).join(", ")}`
                    : ""}
                  {(r.schema_errors || []).length
                    ? ` · schema ${(r.schema_errors || []).length}`
                    : ""}
                </span>
                {r.arbiter_reason ? (
                  <p className="hint llm-routing-reason">{r.arbiter_reason}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
