import { useState } from "react";
import { useApp } from "../../context/AppContext";
import { formatBytes } from "../../utils";
import { WorkflowGuide } from "../WorkflowGuide";

type FlowIntent = "flow1" | "flow2" | "flow3";

const INTENT_CARDS: { id: FlowIntent; title: string; blurb: string }[] = [
  {
    id: "flow1",
    title: "Full master podcast",
    blurb: "Complete episode with VO bridges, sound design, and mastered WAV.",
  },
  {
    id: "flow2",
    title: "Highlight reel",
    blurb: "Up to five clips, montage SFX, ~60s–3min mastered WAV.",
  },
  {
    id: "flow3",
    title: "Show description only",
    blurb: "Third-person blurb for directories — no audio mux.",
  },
];

export function StartTab() {
  const { assets, selectedAsset, setSelectedAsset, refreshHome, startRun, config } = useApp();
  const [flowIntent, setFlowIntent] = useState<FlowIntent>("flow1");
  const intentEnabled = config?.journey_ui?.intent_at_start !== false;

  return (
    <main className="view tab-view">
      <WorkflowGuide />
      <section className="panel hero">
        <h2>Source audio</h2>
        <p className="lead">
          Input files live under <code>ASSETS/</code>. Pick what you are making, then start a new
          execution (<code>exec_001_…</code>).
        </p>
      </section>
      {intentEnabled ? (
        <section className="panel">
          <h3>What are you making?</h3>
          <div className="flow-intent-cards">
            {INTENT_CARDS.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`flow-intent-card${flowIntent === c.id ? " selected" : ""}`}
                data-testid={`flow-intent-${c.id}`}
                onClick={() => setFlowIntent(c.id)}
              >
                <strong>{c.title}</strong>
                <span>{c.blurb}</span>
              </button>
            ))}
          </div>
        </section>
      ) : null}
      <section className="panel">
        <div className="panel-head">
          <h3>Input audio</h3>
          <button type="button" className="btn ghost sm" onClick={() => void refreshHome()}>
            Refresh
          </button>
        </div>
        <div className="asset-list">
          {!assets.length ? (
            <p className="empty-state">
              No input audio in ASSETS/ (outside executions/). Add .wav files and refresh.
            </p>
          ) : (
            assets.map((f) => (
              <div
                key={f.path}
                className={`asset-item${selectedAsset === f.path ? " selected" : ""}`}
                data-testid={`start-asset-${f.name}`}
                onClick={() => setSelectedAsset(f.path)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") setSelectedAsset(f.path);
                }}
                role="button"
                tabIndex={0}
              >
                <div>
                  <strong>{f.name}</strong>
                  <div className="asset-meta">
                    {f.path} · {formatBytes(f.size_bytes)}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn primary sm btn-start"
                  data-testid="new-execution"
                  onClick={(e) => {
                    e.stopPropagation();
                    void startRun(f.path, intentEnabled ? flowIntent : undefined);
                  }}
                >
                  New execution
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </main>
  );
}
