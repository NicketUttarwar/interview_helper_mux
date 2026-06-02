import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";

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

  return (
    <>
      {intent ? (
        <p className="hint">
          Your intent from start: <strong>{intent}</strong> — confirm below.
        </p>
      ) : (
        <p className="hint">Confirm your deliverable.</p>
      )}
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
