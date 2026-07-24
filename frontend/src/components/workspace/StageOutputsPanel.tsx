import { useMemo, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { escapeHtml } from "../../utils";
import type { StageInfo } from "../../types";
import { ArtifactAudio } from "../shared/ArtifactAudio";

type ArtifactRowStatus = "pending" | "partial" | "complete" | "staged" | "n_a" | "skipped";

function artifactRows(stage: StageInfo): {
  path: string;
  label: string;
  status: ArtifactRowStatus;
  phase: string;
  editable: boolean;
  sufficiencyStatus?: string;
}[] {
  if (stage.outputs_view?.length) {
    return stage.outputs_view.map((row) => ({
      path: row.path,
      label: row.label || row.path,
      status: (row.status as ArtifactRowStatus) || "pending",
      phase: row.phase || row.status,
      editable: (stage.editable || []).includes(row.path),
      sufficiencyStatus: row.sufficiency_status,
    }));
  }
  const expected = stage.artifacts || [];
  const statusMap = stage.artifacts_status || {};
  const lifecycle = stage.artifacts_lifecycle || {};
  const editableSet = new Set(stage.editable || []);
  return expected
    .filter((p) => p && !p.endsWith("/"))
    .map((path) => {
      const phase = lifecycle[path];
      let status: ArtifactRowStatus =
        (statusMap[path] as ArtifactRowStatus) || "pending";
      if (phase === "staged") status = "staged";
      if (phase === "n_a" || phase === "skipped") status = "n_a";
      if (phase === "committed" && status === "pending") status = "complete";
      return {
        path,
        label: path.split("/").pop()?.replace(/_/g, " ") || path,
        status,
        phase: phase || status,
        editable: editableSet.has(path),
        sufficiencyStatus: undefined,
      };
    });
}

function statusIcon(status: ArtifactRowStatus): string {
  if (status === "complete" || status === "skipped") return "✓";
  if (status === "partial" || status === "staged") return "◐";
  if (status === "n_a") return "—";
  return "○";
}

function statusLabel(status: ArtifactRowStatus): string {
  if (status === "staged") return "staged — review to save";
  if (status === "n_a") return "n/a (skipped)";
  if (status === "skipped") return "skipped";
  if (status === "pending") return "pending";
  if (status === "partial") return "partial";
  return "saved";
}

function sufficiencyLabel(status?: string): string | null {
  if (!status || status === "ok") return null;
  if (status === "blocking") return "insufficient for downstream";
  if (status === "unknown") return "sufficiency unknown";
  return status;
}

export function StageOutputsPanel({ stage }: { stage: StageInfo }) {
  const { runId, run, openArtifactInEditor, setPipelineSubTab, refreshRun, showToast } = useApp();
  const [activeAudio, setActiveAudio] = useState<string | null>(null);

  const rows = useMemo(() => artifactRows(stage), [stage]);
  const blockingSufficiency = rows.filter((r) => r.sufficiencyStatus === "blocking").length;
  const runSufficiencyBlocking = Number(run?.job?.sufficiency_blocking ?? 0);
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
      {(blockingSufficiency > 0 || runSufficiencyBlocking > 0) && (
        <p className="sufficiency-blocking-banner warning-text sm" role="status">
          {blockingSufficiency > 0
            ? `${blockingSufficiency} artifact(s) fail sufficiency checks — re-run or edit before downstream stages.`
            : `${runSufficiencyBlocking} blocking sufficiency issue(s) in this run.`}
        </p>
      )}
      {run?.working_dir ? (
        <p className="hint sm stage-outputs-wd">
          Working directory: <code>{run.working_dir}</code>
        </p>
      ) : null}

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
          {rows.map(({ path, label, status, editable, sufficiencyStatus }) => {
            const canOpen =
              status === "complete" ||
              status === "staged" ||
              (stageDone && status === "partial");
            const canFillGaps = stageDone && status === "partial" && Boolean(runId);
            return (
              <li
                key={path}
                className={`artifact-checklist-item${status === "pending" ? " missing" : " present"}${status === "partial" || status === "staged" ? " partial" : ""}${status === "n_a" ? " na" : ""}`}
              >
                <span className="artifact-status" aria-hidden>
                  {statusIcon(status)}
                </span>
                <code className="artifact-path">{escapeHtml(path === "(skipped)" ? label : path)}</code>
                {editable && canOpen ? <span className="badge-editable">editable</span> : null}
                {status === "partial" && !stageDone ? (
                  <span className="hint sm">waiting for AI</span>
                ) : null}
                {status === "staged" ? (
                  <span className="badge-staged">in review</span>
                ) : null}
                {sufficiencyLabel(sufficiencyStatus) ? (
                  <span className="badge-sufficiency blocking">{sufficiencyLabel(sufficiencyStatus)}</span>
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
                      {path !== "(skipped)" ? (
                        <button
                          type="button"
                          className="btn ghost sm"
                          onClick={() => void navigator.clipboard?.writeText(path)}
                        >
                          Copy
                        </button>
                      ) : null}
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
                  <span className="hint sm">{statusLabel(status)}</span>
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
            <ArtifactAudio
              className="stage-inline-player"
              src={playUrl(activeAudio)}
              reloadKey={activeAudio}
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
