import { useMemo, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { escapeHtml } from "../../utils";
import type { StageInfo } from "../../types";

type ArtifactRowStatus = "pending" | "partial" | "complete";

function artifactRows(stage: StageInfo): {
  path: string;
  status: ArtifactRowStatus;
  editable: boolean;
}[] {
  const expected = stage.artifacts || [];
  const presentSet = new Set(stage.artifacts_present || []);
  const statusMap = stage.artifacts_status || {};
  const editableSet = new Set(stage.editable || []);
  const paths = [...new Set([...expected, ...Array.from(presentSet)])];
  return paths
    .filter((p) => p && !p.endsWith("/"))
    .map((path) => {
      const status: ArtifactRowStatus =
        statusMap[path] ||
        (presentSet.has(path) ? "complete" : "pending");
      return {
        path,
        status,
        editable: editableSet.has(path),
      };
    });
}

export function StageOutputsPanel({ stage }: { stage: StageInfo }) {
  const { runId, openArtifactInEditor, setPipelineSubTab, refreshRun, showToast } = useApp();
  const [activeAudio, setActiveAudio] = useState<string | null>(null);

  const rows = useMemo(() => artifactRows(stage), [stage]);
  const audioOutputs = stage.audio_outputs_present || [];
  const apiProviders = stage.api_providers || [];
  const stageDone = stage.status === "done";

  const playUrl = (rel: string) =>
    runId ? `/api/runs/${runId}/audio?path=${encodeURIComponent(rel)}` : "";

  if (!rows.length && !audioOutputs.length && !apiProviders.length) {
    return (
      <div className="stage-outputs panel nested">
        <p className="hint">Run this stage to produce outputs. Progress appears in the activity panel.</p>
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
          {rows.map(({ path, status, editable }) => {
            const canOpen = status === "complete" || (stageDone && status === "partial");
            const canFillGaps = stageDone && status === "partial" && Boolean(runId);
            return (
            <li
              key={path}
              className={`artifact-checklist-item${status === "pending" ? " missing" : " present"}${status === "partial" ? " partial" : ""}`}
            >
              <span className="artifact-status" aria-hidden>
                {status === "complete" ? "✓" : status === "partial" ? "◐" : "○"}
              </span>
              <code className="artifact-path">{escapeHtml(path)}</code>
              {editable && canOpen ? <span className="badge-editable">editable</span> : null}
              {status === "partial" && !stageDone ? (
                <span className="hint sm">waiting for AI</span>
              ) : null}
              {status === "partial" && stageDone ? (
                <span className="badge-partial">partial</span>
              ) : null}
              <span className="artifact-checklist-actions">
                {canOpen ? (
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
                ) : null}
                {canFillGaps ? (
                  <button
                    type="button"
                    className="btn ghost sm"
                    onClick={() => {
                      void api(`/api/runs/${runId}/fill-artifact-gaps`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ path }),
                      })
                        .then(() => {
                          showToast(`Filling gaps for ${path}…`);
                          return refreshRun();
                        })
                        .catch((e) =>
                          showToast(e instanceof Error ? e.message : "Fill gaps failed"),
                        );
                    }}
                  >
                    Fill gaps
                  </button>
                ) : null}
                {status === "pending" ? (
                  <span className="hint sm">pending</span>
                ) : null}
              </span>
            </li>
            );
          })}
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
