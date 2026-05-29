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

  return (
    <>
      <p className="hint">Choose deliverable flow.</p>
      <div className="flow-choice">
        <button type="button" className="btn primary" onClick={() => void selectFlow("flow1")}>
          Flow 1 — Full podcast
        </button>
        <button type="button" className="btn primary" onClick={() => void selectFlow("flow2")}>
          Flow 2 — Highlight reel
        </button>
        <button type="button" className="btn primary" onClick={() => void selectFlow("flow3")}>
          Flow 3 — Show description
        </button>
      </div>
    </>
  );
}
