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

interface FileCacheEntry {
  value: string;
  isJson: boolean;
  dirty: boolean;
}

export function WriteApprovalPanel({ stage }: { stage: StageInfo }) {
  const {
    run,
    runId,
    showToast,
    appendClientLog,
    actionBusy,
    activateSubstep,
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
  /** Bumps when cache dirty flags change so the file list can show edited markers. */
  const [cacheRevision, setCacheRevision] = useState(0);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fileCacheRef = useRef<Map<string, FileCacheEntry>>(new Map());
  const selectedPathRef = useRef(selectedPath);
  const editorValueRef = useRef(editorValue);
  const editorDirtyRef = useRef(editorDirty);
  const isJsonRef = useRef(isJson);

  selectedPathRef.current = selectedPath;
  editorValueRef.current = editorValue;
  editorDirtyRef.current = editorDirty;
  isJsonRef.current = isJson;

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

  const bumpCacheRevision = useCallback(() => {
    setCacheRevision((n) => n + 1);
  }, []);

  const writeCacheEntry = useCallback(
    (path: string, entry: FileCacheEntry) => {
      fileCacheRef.current.set(path, entry);
      bumpCacheRevision();
    },
    [bumpCacheRevision],
  );

  const persistCurrentEditorToCache = useCallback(() => {
    const path = selectedPathRef.current;
    if (!path || fileKind(path) === "audio" || !editorDirtyRef.current) return;
    writeCacheEntry(path, {
      value: editorValueRef.current,
      isJson: isJsonRef.current,
      dirty: true,
    });
  }, [writeCacheEntry]);

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

  useEffect(() => {
    fileCacheRef.current.clear();
    bumpCacheRevision();
  }, [stageId, bumpCacheRevision]);

  const loadContent = useCallback(
    async (path: string) => {
      if (!runId || !path || fileKind(path) === "audio") return;

      const cached = fileCacheRef.current.get(path);
      if (cached) {
        setIsJson(cached.isJson);
        setEditorValue(cached.value);
        setEditorDirty(cached.dirty);
        setContentLoading(false);
        return;
      }

      setContentLoading(true);
      const json = isJsonArtifactPath(path);
      setIsJson(json);
      setEditorDirty(false);
      try {
        const data = await api<Record<string, unknown> | { text?: string }>(
          `/api/runs/${runId}/pending-writes/${stageId}/content?path=${encodeURIComponent(path)}`,
        );
        const value = json ? JSON.stringify(data, null, 2) : ((data as { text?: string }).text ?? "");
        setEditorValue(value);
        fileCacheRef.current.set(path, { value, isJson: json, dirty: false });
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
      fileCacheRef.current.clear();
      return;
    }
    if (writePendingForStage || paths.length) {
      setSaveComplete(false);
    }
  }, [writePendingForStage, paths.length, stage.status, stage.id, run]);

  const stageComplete =
    stage.status === "done" && !stageAwaitingWriteApproval(run, stage.id);

  const itrBlocking = run?.job?.itr_blocking_count ?? 0;
  const itrGateActive =
    run?.job?.status === "needs_clarification" &&
    (run?.job?.stage === stage.id || run?.journey?.blocking?.reason === "artifact_clarification");

  const syncEditorToStaging = useCallback(
    async (path: string, value: string, json: boolean) => {
      if (!runId || !path) return;
      if (json) {
        const parsed = JSON.parse(value) as Record<string, unknown>;
        const v = await validateArtifactWrite(path, parsed);
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

  const syncAllDirtyToStaging = useCallback(async () => {
    persistCurrentEditorToCache();

    const dirtyPaths = [...fileCacheRef.current.entries()].filter(
      ([path, entry]) => entry.dirty && fileKind(path) !== "audio",
    );

    for (const [path, entry] of dirtyPaths) {
      await syncEditorToStaging(path, entry.value, entry.isJson);
      fileCacheRef.current.set(path, { ...entry, dirty: false });
    }

    const current = selectedPathRef.current;
    if (current) {
      const entry = fileCacheRef.current.get(current);
      if (entry) setEditorDirty(entry.dirty);
    }
    bumpCacheRevision();
  }, [persistCurrentEditorToCache, syncEditorToStaging, bumpCacheRevision]);

  useEffect(() => {
    registerStepPrimaryPrep("write_approval", syncAllDirtyToStaging);
    return () => registerStepPrimaryPrep("write_approval", null);
  }, [syncAllDirtyToStaging]);

  const selectFile = useCallback(
    (path: string) => {
      if (path === selectedPath) return;
      persistCurrentEditorToCache();
      setSelectedPath(path);
    },
    [selectedPath, persistCurrentEditorToCache],
  );

  const handleEditorChange = useCallback(
    (value: string) => {
      setEditorValue(value);
      setEditorDirty(true);
      const path = selectedPathRef.current;
      if (!path || fileKind(path) === "audio") return;
      writeCacheEntry(path, {
        value,
        isJson: isJsonRef.current,
        dirty: true,
      });
    },
    [writeCacheEntry],
  );

  const isPathDirty = useCallback(
    (path: string) => {
      void cacheRevision;
      if (path === selectedPath && editorDirty) return true;
      return fileCacheRef.current.get(path)?.dirty ?? false;
    },
    [cacheRevision, selectedPath, editorDirty],
  );

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
            Preview each file below. Edits are kept while you switch files and are included when you use{" "}
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
          {(itrBlocking > 0 || itrGateActive) ? (
            <p className="hint write-approval-itr-banner" role="alert">
              {itrBlocking || "Open"} artifact issue(s) block saving.{" "}
              <button
                type="button"
                className="btn link sm"
                onClick={() =>
                  activateSubstep({
                    id: `artifact_clarification:${stage.id}`,
                    stageId: stage.id,
                    status: "todo",
                    label: "Resolve artifact issues",
                    kind: "guidance",
                    source: "runtime",
                  })
                }
              >
                Resolve artifact issues
              </button>
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
              const dirty = isPathDirty(p);
              return (
                <li key={p} className={active ? "active" : ""}>
                  <button
                    type="button"
                    className={`write-approval-file-btn${active ? " active" : ""}${dirty ? " edited" : ""}`}
                    onClick={() => selectFile(p)}
                  >
                    <span className={`write-approval-kind kind-${kind}`}>
                      {KIND_LABEL[kind]}
                    </span>
                    <code className="artifact-path">{p}</code>
                    {dirty ? <span className="write-approval-edited-pill">Edited</span> : null}
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
                    onChange={(e) => handleEditorChange(e.target.value)}
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
