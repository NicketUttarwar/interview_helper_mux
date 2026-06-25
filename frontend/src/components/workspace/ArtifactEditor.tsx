import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { validateArtifactWrite } from "../../schemas/validateArtifact";
import { isJsonArtifactPath } from "../../utils";
import { stageAwaitingWriteApproval } from "../../utils/writeApproval";
import { formatApiError, safeApi } from "../../utils/safeApi";
import type { StageInfo } from "../../types";

function artifactPaths(stage: StageInfo): string[] {
  return [...new Set([...(stage.editable || []), ...(stage.artifacts || [])])].filter(
    (p) => p && !p.endsWith("/") && (isJsonArtifactPath(p) || p.endsWith(".md") || p.endsWith(".txt")),
  );
}

export function ArtifactEditor() {
  const {
    run,
    selectedStage,
    refreshRun,
    showToast,
    confirm,
    appendClientLog,
  } = useApp();
  const [paths, setPaths] = useState<string[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [editorValue, setEditorValue] = useState("");
  const [isJson, setIsJson] = useState(true);
  const [status, setStatus] = useState("");
  const [loadedFromStaging, setLoadedFromStaging] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!selectedStage) {
      setPaths([]);
      setSelectedPath("");
      setEditorValue("");
      setStatus("No editable artifacts for this stage yet.");
      return;
    }
    const p = artifactPaths(selectedStage);
    setPaths(p);
    if (p.length) {
      setSelectedPath(p[0]);
    } else {
      setSelectedPath("");
      setEditorValue("");
      setStatus("No editable artifacts for this stage yet.");
    }
  }, [selectedStage]);

  const loadArtifact = useCallback(
    async (path: string) => {
      if (!run || !path) return;
      setIsJson(isJsonArtifactPath(path));
      setStatus(`Loading ${path}…`);
      const applyPayload = (
        data: Record<string, unknown> | { text?: string },
        source: string,
      ) => {
        if (isJsonArtifactPath(path)) {
          setEditorValue(JSON.stringify(data, null, 2));
        } else {
          setEditorValue((data as { text?: string }).text ?? "");
        }
        setStatus(`${source}: ${path}`);
      };
      try {
        const data = await safeApi(
          api<Record<string, unknown> | { text?: string }>(
            `/api/runs/${run.run_id}/artifact?path=${encodeURIComponent(path)}`,
          ),
          {
            label: `Load ${path}`,
            onError: (msg) => {
              appendClientLog(msg, "error", selectedStage?.id);
            },
          },
        );
        if (data) {
          setLoadedFromStaging(false);
          applyPayload(data, "Loaded");
          return;
        }
        const pendingStage =
          run.job?.pending_write_stage || run.job?.stage || undefined;
        if (pendingStage) {
          const staged = await safeApi(
            api<Record<string, unknown> | { text?: string }>(
              `/api/runs/${run.run_id}/pending-writes/${pendingStage}/content?path=${encodeURIComponent(path)}`,
            ),
            { label: `Load staged ${path}` },
          );
          if (staged) {
            setLoadedFromStaging(true);
            applyPayload(staged, "Loaded staged copy (pending=1)");
            return;
          }
        }
        setLoadedFromStaging(false);
        setEditorValue("");
        const msg = `${path} not found — run this stage first.`;
        setStatus(msg);
        showToast(msg, "error");
      } catch (reason) {
        setEditorValue("");
        const msg = formatApiError(reason, `Load ${path}`);
        setStatus(msg);
        showToast(msg, "error");
        appendClientLog(msg, "error", selectedStage?.id);
      }
    },
    [run, selectedStage?.id, showToast, appendClientLog],
  );

  useEffect(() => {
    if (selectedPath) void loadArtifact(selectedPath);
  }, [selectedPath, loadArtifact]);

  useEffect(() => {
    const handler = (e: Event) => {
      const path = (e as CustomEvent<{ path: string }>).detail?.path;
      if (!path) return;
      if (!paths.includes(path)) {
        setPaths((prev) => [...prev, path]);
      }
      setSelectedPath(path);
    };
    window.addEventListener("handoff-open", handler);
    return () => window.removeEventListener("handoff-open", handler);
  }, [paths]);

  const saveArtifact = async () => {
    if (!run || !selectedPath || !selectedStage) return;
    if (stageAwaitingWriteApproval(run, selectedStage.id)) {
      appendClientLog(
        "Use Save all files & continue on the step footer to write staged outputs to disk.",
        "info",
        selectedStage.id,
      );
      showToast("Staged files need review approval — use Save all files & continue below.");
      return;
    }
    const invalidate = (await confirm(
      "Save to disk? Downstream stages may need re-run.",
    ))
      ? selectedStage.id
      : null;
    setSaving(true);
    showToast(`Saving ${selectedPath}…`, "info");
    try {
      if (isJson) {
        let data: unknown;
        try {
          data = JSON.parse(editorValue);
        } catch {
          showToast("Invalid JSON");
          return;
        }
        const v = validateArtifactWrite(selectedPath, data);
        if (!v.ok) {
          setStatus(`Schema errors:\n${v.errors.join("\n")}`);
          showToast("Fix schema errors before saving");
          return;
        }
        await api(`/api/runs/${run.run_id}/artifact`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            path: selectedPath,
            data,
            invalidate_from: invalidate,
          }),
        });
      } else {
        await api(`/api/runs/${run.run_id}/artifact/text`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            path: selectedPath,
            text: editorValue,
            invalidate_from: invalidate,
          }),
        });
      }
      showToast("Saved");
      appendClientLog(`Saved artifact ${selectedPath}`, "success");
      await refreshRun();
    } catch (e) {
      const msg = formatApiError(e, "Save artifact");
      showToast(msg, "error");
      appendClientLog(msg, "error", selectedStage.id);
    } finally {
      setSaving(false);
    }
  };

  const stagedAwaitingSave =
    loadedFromStaging || (selectedStage && stageAwaitingWriteApproval(run, selectedStage.id));

  return (
    <div className="panel artifacts-panel">
      <div className="panel-head">
        <h3>File editor</h3>
        {stagedAwaitingSave ? (
          <span className="stage-status-pill attention" title="Staged copy — use Save all files & continue on the step footer to commit">
            Staged (not saved)
          </span>
        ) : null}
        <select
          className="select"
          value={selectedPath}
          onChange={(e) => setSelectedPath(e.target.value)}
        >
          {paths.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        {!stagedAwaitingSave ? (
          <button
            type="button"
            className="btn primary sm"
            disabled={saving || !selectedPath}
            onClick={() => void saveArtifact()}
          >
            {saving ? (
              <>
                <span className="spinner-inline" aria-hidden /> Saving…
              </>
            ) : (
              "Save to file"
            )}
          </button>
        ) : null}
      </div>
      <textarea
        className="artifact-editor"
        spellCheck={false}
        value={editorValue}
        onChange={(e) => setEditorValue(e.target.value)}
      />
      <p className="save-status">{status}</p>
    </div>
  );
}
