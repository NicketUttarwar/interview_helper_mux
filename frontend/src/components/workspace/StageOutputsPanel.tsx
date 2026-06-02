import { useMemo, useState } from "react";
import { useApp } from "../../context/AppContext";
import { escapeHtml } from "../../utils";
import type { StageInfo } from "../../types";

function artifactRows(stage: StageInfo): { path: string; present: boolean; editable: boolean }[] {
  const expected = stage.artifacts || [];
  const presentSet = new Set(stage.artifacts_present || []);
  const editableSet = new Set(stage.editable || []);
  const paths = [...new Set([...expected, ...Array.from(presentSet)])];
  return paths
    .filter((p) => p && !p.endsWith("/"))
    .map((path) => ({
      path,
      present: presentSet.has(path),
      editable: editableSet.has(path),
    }));
}

export function StageOutputsPanel({ stage }: { stage: StageInfo }) {
  const { runId, openArtifactInEditor, setPipelineSubTab } = useApp();
  const [activeAudio, setActiveAudio] = useState<string | null>(null);

  const rows = useMemo(() => artifactRows(stage), [stage]);
  const audioOutputs = stage.audio_outputs_present || [];
  const apiProviders = stage.api_providers || [];

  const playUrl = (rel: string) =>
    runId ? `/api/runs/${runId}/audio?path=${encodeURIComponent(rel)}` : "";

  if (!rows.length && !audioOutputs.length && !apiProviders.length) {
    return (
      <div className="stage-outputs panel nested">
        <p className="hint">Run this stage to produce outputs. Progress appears in Logs.</p>
      </div>
    );
  }

  return (
    <div className="stage-outputs panel nested">
      <h3 className="stage-outputs-title">Stage outputs</h3>

      {apiProviders.length > 0 ? (
        <div className="stage-api-chips">
          <span className="hint">Uses:</span>
          {apiProviders.map((p) => (
            <span key={p} className="api-chip">
              {p}
            </span>
          ))}
        </div>
      ) : null}

      {rows.length > 0 ? (
        <ul className="artifact-checklist">
          {rows.map(({ path, present, editable }) => (
            <li
              key={path}
              className={`artifact-checklist-item${present ? " present" : " missing"}`}
            >
              <span className="artifact-status" aria-hidden>
                {present ? "✓" : "○"}
              </span>
              <code className="artifact-path">{escapeHtml(path)}</code>
              {editable ? <span className="badge-editable">editable</span> : null}
              <span className="artifact-checklist-actions">
                {present ? (
                  <>
                    <button
                      type="button"
                      className="btn ghost sm"
                      onClick={() => openArtifactInEditor(path)}
                    >
                      Open
                    </button>
                    <button
                      type="button"
                      className="btn ghost sm"
                      onClick={() => void navigator.clipboard?.writeText(path)}
                    >
                      Copy
                    </button>
                  </>
                ) : (
                  <span className="hint sm">pending</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {audioOutputs.length > 0 ? (
        <div className="stage-audio-outputs">
          <p className="hint">
            <strong>Audio</strong>
          </p>
          {audioOutputs.map((path) => (
            <div key={path} className="stage-audio-row">
              <button
                type="button"
                className={`btn ghost sm${activeAudio === path ? " active" : ""}`}
                onClick={() => setActiveAudio(path)}
              >
                {path.split("/").pop()}
              </button>
            </div>
          ))}
          {activeAudio ? (
            <audio
              controls
              className="audio-player stage-inline-player"
              src={playUrl(activeAudio)}
            />
          ) : null}
        </div>
      ) : null}

      {(stage.editable?.length || 0) > 0 ? (
        <button
          type="button"
          className="btn ghost sm stage-files-link"
          onClick={() => setPipelineSubTab("files")}
        >
          Open file editor tab
        </button>
      ) : null}
    </div>
  );
}
