import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { validateArtifactWrite } from "../../schemas/validateArtifact";
import { isJsonArtifactPath } from "../../utils";
import { isWriteApprovalSaveInProgress } from "../../utils/jobStatus";
import { writeApprovalSaveInProgressLabel } from "../../utils/writeApprovalLabels";
import { registerStepPrimaryPrep } from "../../utils/stepPrimaryPrep";
import {
  resolvePendingWritePaths,
  stageAwaitingWriteApproval,
} from "../../utils/writeApproval";
import { formatApiError } from "../../utils/safeApi";
import { ReviewPanelControls } from "./ReviewPanelControls";
import type { StageInfo } from "../../types";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";

function fileKind(path: string): "audio" | "json" | "text" {
  if (path.endsWith(".wav")) return "audio";
  if (path.endsWith(".json")) return "json";
  return "text";
}

const KIND_LABEL: Record<string, string> = {
  audio: "Audio",
  json: "JSON",
  text: "Text",
};

export function WriteApprovalPanel({ stage }: { stage: StageInfo }) {
  const {
    run,
    runId,
    showToast,
    appendClientLog,
    actionBusy,
  } = useApp();
  const [apiPaths, setApiPaths] = useState<string[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [editorValue, setEditorValue] = useState("");
  const [contentLoading, setContentLoading] = useState(false);
  const [isJson, setIsJson] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editorDirty, setEditorDirty] = useState(false);
  const [saveComplete, setSaveComplete] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stageId = run?.job?.pending_write_stage || run?.job?.stage || stage.id;
  const writePendingForStage = stageAwaitingWriteApproval(run, stage.id);
  const saveInProgress = isWriteApprovalSaveInProgress(run, {
    actionBusy,
    stageId: stage.id,
  });

  const paths = useMemo(
    () => resolvePendingWritePaths(run, stageId, apiPaths),
    [run, stageId, apiPaths],
  );

  const runRef = useRef(run);
  runRef.current = run;

  const loadPaths = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setLoadError(null);
    try {
      const data = await api<{ paths?: string[] }>(
        `/api/runs/${runId}/pending-writes/${stageId}`,
      );
      setApiPaths(data.paths || []);
    } catch (e) {
      const fallback = resolvePendingWritePaths(runRef.current, stageId);
      if (!fallback.length) {
        setApiPaths([]);
        setLoadError(e instanceof ApiError ? e.message : "Could not load staged files");
      }
    } finally {
      setLoading(false);
    }
  }, [runId, stageId]);

  useEffect(() => {
    void loadPaths();
  }, [loadPaths]);

  const loadContent = useCallback(
    async (path: string) => {
      if (!runId || !path || fileKind(path) === "audio") return;
      setContentLoading(true);
      setIsJson(isJsonArtifactPath(path));
      setEditorDirty(false);
      try {
        const data = await api<Record<string, unknown> | { text?: string }>(
          `/api/runs/${runId}/pending-writes/${stageId}/content?path=${encodeURIComponent(path)}`,
        );
        if (isJsonArtifactPath(path)) {
          setEditorValue(JSON.stringify(data, null, 2));
        } else {
          setEditorValue((data as { text?: string }).text ?? "");
        }
      } catch (reason) {
        setEditorValue("");
        const msg = formatApiError(reason, `Load ${path}`);
        showToast(msg, "error");
        appendClientLog(msg, "error", stageId);
      } finally {
        setContentLoading(false);
      }
    },
    [runId, stageId, showToast, appendClientLog],
  );

  useEffect(() => {
    if (selectedPath && fileKind(selectedPath) !== "audio") void loadContent(selectedPath);
  }, [selectedPath, loadContent]);

  useEffect(() => {
    setSelectedPath((prev) => {
      if (prev && paths.includes(prev)) return prev;
      return paths[0] || "";
    });
  }, [paths]);

  useEffect(() => {
    if (stage.status === "done" && !stageAwaitingWriteApproval(run, stage.id)) {
      setSaveComplete(true);
      setApiPaths([]);
      return;
    }
    if (writePendingForStage || paths.length) {
      setSaveComplete(false);
    }
  }, [writePendingForStage, paths.length, stage.status, stage.id, run]);

  const stageComplete =
    stage.status === "done" && !stageAwaitingWriteApproval(run, stage.id);

  const syncEditorToStaging = useCallback(
    async (path: string, value: string, json: boolean) => {
      if (!runId || !path) return;
      if (json) {
        const parsed = JSON.parse(value) as Record<string, unknown>;
        const v = validateArtifactWrite(path, parsed);
        if (!v.ok) throw new Error(`Validation: ${v.errors[0]}`);
        await api(`/api/runs/${runId}/pending-writes/${stageId}/content`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path, data: parsed }),
        });
      } else {
        await api(`/api/runs/${runId}/pending-writes/${stageId}/content`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path, text: value }),
        });
      }
    },
    [runId, stageId],
  );

  useEffect(() => {
    registerStepPrimaryPrep("write_approval", async () => {
      if (!editorDirty || !selectedPath || fileKind(selectedPath) === "audio") return;
      await syncEditorToStaging(selectedPath, editorValue, isJson);
      setEditorDirty(false);
    });
    return () => registerStepPrimaryPrep("write_approval", null);
  }, [
    editorDirty,
    selectedPath,
    editorValue,
    isJson,
    syncEditorToStaging,
  ]);

  if (saveComplete || stageComplete) {
    return (
      <section
        id="write-approval-panel"
        className="write-approval-panel write-approval-panel--done panel-inset"
        aria-label="Save review complete"
      >
        <StepDoneBanner variant="substep" title="Files saved — step complete" />
      </section>
    );
  }

  if (!writePendingForStage && !paths.length && !loading && !stageComplete) return null;

  return (
    <section
      id="write-approval-panel"
      className="write-approval-panel panel-inset"
      aria-label="Review outputs before saving"
    >
      <div className="write-approval-head">
        <div>
          <h3 className="stage-outputs-title">Save to working directory — review outputs before saving</h3>
          <p className="hint write-approval-substep">
            Substep: <strong>Review staged outputs</strong>
          </p>
          <p className="hint">
            <strong>{stage.title}</strong>
            {paths.length
              ? ` staged ${paths.length} file${paths.length === 1 ? "" : "s"}.`
              : " is waiting for your approval before files are saved to disk."}{" "}
            Preview each file below. Edits are included when you use{" "}
            <strong>Save all files &amp; continue</strong> at the bottom of this step.
          </p>
          {run?.working_dir ? (
            <p className="hint sm write-approval-wd" title={run.working_dir}>
              Working directory:{" "}
              <code>
                {run.working_dir.includes("/executions/")
                  ? `executions/${run.working_dir.split("/executions/").pop()}`
                  : run.working_dir}
              </code>
            </p>
          ) : null}
          {saveInProgress ? (
            <p className="hint write-approval-saving-banner" role="status" aria-live="polite">
              <span className="spinner-inline" aria-hidden />
              {writeApprovalSaveInProgressLabel(paths.length)} No action needed — watch Activity (Live).
            </p>
          ) : paths.some((p) => p.endsWith(".wav")) ? (
            <p className="hint sm write-approval-large-wav">
              Large audio files may take a minute to save — the button will show progress when saving starts.
            </p>
          ) : null}
        </div>
        <ReviewPanelControls />
      </div>

      {loading ? (
        <p className="hint empty-state">
          <span className="spinner-inline" aria-hidden /> Loading staged files…
        </p>
      ) : loadError && !paths.length ? (
        <div className="write-approval-error">
          <p className="hint" role="alert">
            {loadError}
          </p>
          <button type="button" className="btn ghost sm" onClick={() => void loadPaths()}>
            Retry
          </button>
        </div>
      ) : null}

      {paths.length ? (
        <div className="write-approval-layout">
          <ul className="write-approval-file-list">
            {paths.map((p) => {
              const kind = fileKind(p);
              const active = selectedPath === p;
              return (
                <li key={p} className={active ? "active" : ""}>
                  <button
                    type="button"
                    className={`write-approval-file-btn${active ? " active" : ""}`}
                    onClick={() => setSelectedPath(p)}
                  >
                    <span className={`write-approval-kind kind-${kind}`}>
                      {KIND_LABEL[kind]}
                    </span>
                    <code className="artifact-path">{p}</code>
                  </button>
                </li>
              );
            })}
          </ul>

          <div className="write-approval-preview">
            {selectedPath && fileKind(selectedPath) === "audio" && run ? (
              <audio
                ref={audioRef}
                controls
                className="write-approval-audio"
                src={`/api/runs/${run.run_id}/audio?path=${encodeURIComponent(selectedPath)}&pending=1&pending_stage=${encodeURIComponent(stageId)}`}
              />
            ) : selectedPath ? (
              <div className="write-approval-editor">
                {contentLoading ? (
                  <p className="hint">
                    <span className="spinner-inline" aria-hidden /> Loading file content…
                  </p>
                ) : (
                  <textarea
                    className="artifact-editor-textarea"
                    value={editorValue}
                    onChange={(e) => {
                      setEditorValue(e.target.value);
                      setEditorDirty(true);
                    }}
                    rows={14}
                    placeholder="Staged file content appears here…"
                  />
                )}
              </div>
            ) : (
              <p className="hint empty-state">Select a file to preview.</p>
            )}
          </div>
        </div>
      ) : null}

      {saveInProgress ? (
        <p className="hint sm write-approval-running-hint" role="status" aria-live="polite">
          <span className="spinner-inline" aria-hidden />
          {writeApprovalSaveInProgressLabel(paths.length)}
        </p>
      ) : null}
    </section>
  );
}
