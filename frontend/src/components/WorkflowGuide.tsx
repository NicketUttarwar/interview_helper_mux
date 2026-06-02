import { useState } from "react";

const STORAGE_KEY = "workflow_guide_collapsed";

const STEPS = [
  { phase: "Start", detail: "Pick audio and output type." },
  { phase: "Prepare", detail: "Transcribe → fix STT clips (G0)." },
  { phase: "Understand", detail: "Analysis + Story Board profile." },
  { phase: "Complete", detail: "VO pickups (G1) → confirm output (G2)." },
  { phase: "Create → Ship", detail: "Preview, sound, export master or blurb." },
];

export function WorkflowGuide() {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(STORAGE_KEY) === "1",
  );

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
  };

  return (
    <section className="panel workflow-guide">
      <div className="panel-head workflow-guide-head">
        <h3>How this app works</h3>
        <button type="button" className="btn ghost sm" onClick={toggle}>
          {collapsed ? "Show guide" : "Hide guide"}
        </button>
      </div>
      {!collapsed ? (
        <>
          <ol className="workflow-steps compact">
            {STEPS.map((s, i) => (
              <li key={s.phase}>
                <span className="workflow-step-num">{i + 1}</span>
                <div>
                  <strong>{s.phase}</strong>
                  <span className="muted"> — {s.detail}</span>
                </div>
              </li>
            ))}
          </ol>
          <p className="hint workflow-tip">
            Follow the <strong>command bar</strong> under the header on every tab.
            <strong> Action</strong> opens checkpoints (transcript, VO, APIs).
          </p>
        </>
      ) : (
        <p className="hint workflow-tip-collapsed">
          Use the command bar and Pipeline tab — expand this guide anytime.
        </p>
      )}
    </section>
  );
}
