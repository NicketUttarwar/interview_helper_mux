import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { LLM_STAGES } from "../../utils";
import type { LlmRoutingAttempt } from "../../types";

export function StageDetail() {
  const { run, selectedStage, openActionModal, pendingActionCount } = useApp();
  const [llmAttempts, setLlmAttempts] = useState<LlmRoutingAttempt[]>([]);

  useEffect(() => {
    if (!run || !selectedStage || !LLM_STAGES.has(selectedStage.id)) {
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
  }, [run, selectedStage]);

  if (!selectedStage) {
    return (
      <div className="panel stage-detail">
        <h2>Select a stage</h2>
        <p className="hint">Choose a pipeline stage from the sidebar.</p>
      </div>
    );
  }

  return (
    <div className="panel stage-detail stage-detail-slim">
      <h2>{selectedStage.title}</h2>
      <p className="lead">{selectedStage.description}</p>

      {pendingActionCount > 0 ? (
        <div className="stage-action-cta">
          <p className="hint">Operator action is required for this execution.</p>
          <button type="button" className="btn primary sm" onClick={openActionModal}>
            Open checkpoint
          </button>
        </div>
      ) : null}

      {llmAttempts.length > 0 ? (
        <div className="llm-routing-panel">
          <p className="hint">
            <strong>LLM routing</strong>
          </p>
          <ul className="llm-routing-list">
            {llmAttempts.map((r, i) => (
              <li key={i}>
                <code>{r.task_kind || "primary"}</code> verdict=
                <strong>{r.verdict || "—"}</strong> shards={r.shard_count || 0}{" "}
                trunc={(r.truncation_flags || []).join(",") || "none"}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
