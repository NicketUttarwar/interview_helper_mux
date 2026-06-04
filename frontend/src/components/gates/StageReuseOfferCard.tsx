import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { ReuseCandidate, StageInfo } from "../../types";

export function StageReuseOfferCard({
  stage,
  candidates,
}: {
  stage: StageInfo;
  candidates: ReuseCandidate[];
}) {
  const { runId, refreshRun, executeJob, runNextStage, showToast } = useApp();
  const [submitting, setSubmitting] = useState(false);

  if (!candidates.length) return null;

  const submit = async (action: "accept" | "decline", sourceRunId?: string) => {
    if (!runId || submitting) return;
    setSubmitting(true);
    try {
      await api(`/api/runs/${runId}/stages/${stage.id}/reuse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          source_run_id: sourceRunId,
        }),
      });
      await refreshRun();
      if (action === "decline") {
        showToast(`Running ${stage.title} fresh.`);
        await executeJob({ mode: "stage", stage: stage.id });
      } else {
        showToast(`Reused ${stage.title} from ${sourceRunId} — continuing to next step.`);
        await runNextStage();
      }
    } catch (e) {
      showToast(e instanceof ApiError ? e.message : "Reuse action failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="quality-offer-card stage-reuse-offer">
      <h4>Reuse previous execution?</h4>
      <p className="hint">
        The same source audio was used in earlier runs. You can copy completed outputs for{" "}
        <strong>{stage.title}</strong> instead of running this step again.
      </p>
      <ul className="stage-reuse-candidate-list">
        {candidates.map((c) => (
          <li key={c.run_id}>
            <span className="mono">{c.run_id}</span>
            {c.execution_number != null ? (
              <span className="muted"> · exec #{c.execution_number}</span>
            ) : null}
            {c.paths.length ? (
              <span className="muted"> · {c.paths.length} file(s)</span>
            ) : null}
            <button
              type="button"
              className="btn primary sm"
              disabled={submitting}
              onClick={() => void submit("accept", c.run_id)}
            >
              Reuse from this run
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="btn ghost sm"
        disabled={submitting}
        onClick={() => void submit("decline")}
      >
        Run fresh
      </button>
    </div>
  );
}
