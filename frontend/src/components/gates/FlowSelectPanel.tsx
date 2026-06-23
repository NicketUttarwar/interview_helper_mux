import { useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatApiError } from "../../utils/safeApi";

const FLOW_LABELS: Record<string, string> = {
  flow1: "Flow 1 — Full podcast",
  flow2: "Flow 2 — Highlight reel",
  flow3: "Flow 3 — Show description",
};

export function FlowSelectPanel() {
  const {
    run,
    refreshRun,
    runNextStage,
    showToast,
    closeActionModal,
    jobRunning,
    actionBusy,
  } = useApp();
  const [submitting, setSubmitting] = useState(false);

  const busy = submitting || jobRunning || actionBusy;

  const selectFlow = async (flow: string) => {
    if (!run || busy) return;
    setSubmitting(true);
    try {
      await api(`/api/runs/${run.run_id}/flow`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flow }),
      });
      const label = FLOW_LABELS[flow] || flow;
      showToast(`Selected ${label} — continuing pipeline.`);
      await refreshRun();
      closeActionModal();
      await runNextStage();
    } catch (e) {
      showToast(formatApiError(e, "Flow selection"), "error");
    } finally {
      setSubmitting(false);
    }
  };

  const intent = run?.flow_intent || run?.meta?.flow_intent;
  const intentValid =
    intent === "flow1" || intent === "flow2" || intent === "flow3";

  return (
    <>
      {intent ? (
        <p className="hint">
          Planning intent from Start: <strong>{intent}</strong> — confirm below or
          choose a different deliverable.
        </p>
      ) : (
        <p className="hint">Confirm your deliverable.</p>
      )}
      {intentValid ? (
        <button
          type="button"
          className="btn primary"
          data-testid="select-flow-use-intent"
          disabled={busy}
          onClick={() => void selectFlow(intent!)}
        >
          {submitting ? (
            <>
              <span className="spinner-inline" aria-hidden /> Saving…
            </>
          ) : (
            <>Use planned choice ({FLOW_LABELS[intent!] || intent})</>
          )}
        </button>
      ) : null}
      <div className="flow-choice">
        {(["flow1", "flow2", "flow3"] as const).map((flow) => (
          <button
            key={flow}
            type="button"
            className={`btn${intent === flow ? " primary" : " ghost"}`}
            data-testid={`select-flow-${flow}`}
            disabled={busy}
            onClick={() => void selectFlow(flow)}
          >
            {submitting ? (
              <span className="spinner-inline" aria-hidden />
            ) : null}
            {FLOW_LABELS[flow]}
            {intent === flow ? " (planned)" : ""}
          </button>
        ))}
      </div>
    </>
  );
}
