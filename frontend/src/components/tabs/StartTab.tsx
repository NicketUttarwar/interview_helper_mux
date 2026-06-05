import { useState } from "react";
import { useApp } from "../../context/AppContext";
import { formatBytes } from "../../utils";
import { InfoTooltip } from "../InfoTooltip";

type FlowIntent = "flow1" | "flow2" | "flow3";

const INTENT_CARDS: { id: FlowIntent; title: string; tooltip: string }[] = [
  {
    id: "flow1",
    title: "Full podcast",
    tooltip: "Complete episode with VO bridges, sound design, and mastered WAV.",
  },
  {
    id: "flow2",
    title: "Highlights",
    tooltip: "Up to five clips with montage SFX (~60s–3min mastered WAV).",
  },
  {
    id: "flow3",
    title: "Description",
    tooltip: "Third-person show blurb for directories — no audio output.",
  },
];

export function StartTab() {
  const { assets, selectedAsset, setSelectedAsset, refreshHome, startRun, config } = useApp();
  const [flowIntent, setFlowIntent] = useState<FlowIntent>("flow1");
  const intentEnabled = config?.journey_ui?.intent_at_start !== false;

  return (
    <main className="view tab-view">
      <section className="panel hero hero-compact">
        <h2>
          New execution
          <InfoTooltip text="Place .wav files in ASSETS/, pick your output type, then start." />
        </h2>
      </section>
      {intentEnabled ? (
        <section className="panel panel-compact">
          <h3>
            Output type
            <InfoTooltip text="You can change this later at the Complete step (G2)." />
          </h3>
          <div className="flow-intent-cards">
            {INTENT_CARDS.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`flow-intent-card${flowIntent === c.id ? " selected" : ""}`}
                data-testid={`flow-intent-${c.id}`}
                title={c.tooltip}
                onClick={() => setFlowIntent(c.id)}
              >
                <strong>{c.title}</strong>
                <InfoTooltip text={c.tooltip} label={`About ${c.title}`} />
              </button>
            ))}
          </div>
        </section>
      ) : null}
      <section className="panel panel-compact">
        <div className="panel-head">
          <h3>Source audio</h3>
          <button type="button" className="btn ghost sm" onClick={() => void refreshHome()}>
            Refresh
          </button>
        </div>
        <div className="asset-list">
          {!assets.length ? (
            <p className="empty-state">No audio in ASSETS/. Add .wav files and refresh.</p>
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
                  <div className="asset-meta">{formatBytes(f.size_bytes)}</div>
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
                  Start
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </main>
  );
}
