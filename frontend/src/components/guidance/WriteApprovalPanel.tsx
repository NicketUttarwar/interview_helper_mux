import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { validateArtifactWrite } from "../../schemas/validateArtifact";
import { isJsonArtifactPath } from "../../utils";
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
    approveWriteAndContinue,
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
  const [saveError, setSaveError] = useState<string | null>(null);

  const stageId = run?.job?.pending_write_stage || run?.job?.stage || stage.id;
  const writePendingForStage = stageAwaitingWriteApproval(run, stage.id);

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
    if (writePendingForStage || paths.length) {
      setSaveComplete(false);
      setSaveError(null);
    }
  }, [writePendingForStage, paths.length]);

  const syncEditorToStaging = async (path: string, value: string, json: boolean) => {
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
  };

  const saveEdit = async () => {
    if (!selectedPath) return;
    try {
      await syncEditorToStaging(selectedPath, editorValue, isJson);
      setEditorDirty(false);
      showToast(`Updated ${selectedPath}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Save failed";
      showToast(msg, "error");
    }
  };

  const approve = async () => {
    if (actionBusy) return;
    setSaveError(null);
    try {
      if (editorDirty && selectedPath && fileKind(selectedPath) !== "audio") {
        await syncEditorToStaging(selectedPath, editorValue, isJson);
        setEditorDirty(false);
      }
      const ok = await approveWriteAndContinue(stageId);
      if (ok) setSaveComplete(true);
      else
        setSaveError(
          "Save did not complete — check Activity log and retry from the sidebar substep.",
        );
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Approve failed";
      setSaveError(msg);
      showToast(msg, "error");
      appendClientLog(msg, "error", stageId);
    }
  };

  const discard = async () => {
    if (!runId || actionBusy) return;
    try {
      await api(`/api/runs/${runId}/pending-writes/${stageId}/discard`, {
        method: "POST",
      });
      showToast("Discarded staged outputs — re-run this step when ready.");
      appendClientLog(`Write approval discarded for ${stageId}`, "info");
      await loadPaths();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Discard failed";
      showToast(msg, "error");
      appendClientLog(msg, "error", stageId);
    }
  };

  if (saveComplete) {
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

  if (!writePendingForStage && !paths.length && !loading) return null;

  const saveDisabled = actionBusy || !paths.length;

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
            Substep:{" "}
            <strong>
              {paths.length
                ? `Save ${paths.length} file${paths.length === 1 ? "" : "s"} & continue`
                : "Save review before continuing"}
            </strong>
          </p>
          <p className="hint">
            <strong>{stage.title}</strong>
            {paths.length
              ? ` staged ${paths.length} file${paths.length === 1 ? "" : "s"}.`
              : " is waiting for your approval before files are saved to disk."}{" "}
            Files are pre-loaded below — edit if needed, then save to disk.
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
        </div>
        <ReviewPanelControls requirePending={false} />
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

      {saveError ? (
        <div className="write-approval-error">
          <p className="hint" role="alert">
            {saveError}
          </p>
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
                <button
                  type="button"
                  className="btn ghost sm"
                  disabled={contentLoading || !editorDirty}
                  onClick={() => void saveEdit()}
                >
                  Save edit to staging
                </button>
              </div>
            ) : (
              <p className="hint empty-state">Select a file to preview.</p>
            )}
          </div>
        </div>
      ) : null}

      <div className="write-approval-actions">
        <button
          type="button"
          className="btn primary"
          data-testid="write-approval-save-continue"
          disabled={saveDisabled}
          onClick={() => void approve()}
        >
          {actionBusy ? (
            <>
              <span className="spinner-inline" aria-hidden /> Saving…
            </>
          ) : paths.length ? (
            `Save ${paths.length} file${paths.length === 1 ? "" : "s"} & continue`
          ) : (
            "Save & continue"
          )}
        </button>
        <button
          type="button"
          className="btn ghost sm"
          disabled={actionBusy}
          onClick={() => void discard()}
        >
          Discard &amp; re-run
        </button>
      </div>
    </section>
  );
}
