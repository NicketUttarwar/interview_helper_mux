import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";

const FLOW_LABELS: Record<string, string> = {
  flow1: "Flow 1 — Full podcast",
  flow2: "Flow 2 — Highlight reel",
  flow3: "Flow 3 — Show description",
};

export function FlowSelectPanel() {
  const { run, refreshRun } = useApp();

  const selectFlow = async (flow: string) => {
    if (!run) return;
    await api(`/api/runs/${run.run_id}/flow`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ flow }),
    });
    await refreshRun();
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
          onClick={() => void selectFlow(intent!)}
        >
          Use planned choice ({FLOW_LABELS[intent!] || intent})
        </button>
      ) : null}
      <div className="flow-choice">
        <button type="button" className="btn primary" data-testid="select-flow-flow1" onClick={() => void selectFlow("flow1")}>
          Flow 1 — Full podcast
        </button>
        <button type="button" className="btn primary" data-testid="select-flow-flow2" onClick={() => void selectFlow("flow2")}>
          Flow 2 — Highlight reel
        </button>
        <button type="button" className="btn primary" data-testid="select-flow-flow3" onClick={() => void selectFlow("flow3")}>
          Flow 3 — Show description
        </button>
      </div>
    </>
  );
}
