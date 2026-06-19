import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { validateArtifactWrite } from "../../schemas/validateArtifact";
import { isJsonArtifactPath } from "../../utils";
import { stageAwaitingWriteApproval } from "../../utils/writeApproval";
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
        const data = await api<Record<string, unknown> | { text?: string }>(
          `/api/runs/${run.run_id}/artifact?path=${encodeURIComponent(path)}`,
        );
        applyPayload(data, "Loaded");
      } catch {
        const pendingStage =
          run.job?.pending_write_stage || run.job?.stage || undefined;
        if (pendingStage) {
          try {
            const staged = await api<Record<string, unknown> | { text?: string }>(
              `/api/runs/${run.run_id}/pending-writes/${pendingStage}/content?path=${encodeURIComponent(path)}`,
            );
            applyPayload(staged, "Loaded staged copy");
            return;
          } catch {
            /* fall through */
          }
        }
        setEditorValue("");
        setStatus(`${path} not found — run this stage first.`);
      }
    },
    [run],
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
        "Use Save & continue on the review panel to write staged outputs to disk.",
        "info",
        selectedStage.id,
      );
      showToast("Staged files need review approval — use Save & continue above.");
      return;
    }
    const invalidate = (await confirm(
      "Save to disk? Downstream stages may need re-run.",
    ))
      ? selectedStage.id
      : null;
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
      showToast(e instanceof Error ? e.message : "Save failed");
    }
  };

  return (
    <div className="panel artifacts-panel">
      <div className="panel-head">
        <h3>File editor</h3>
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
        <button type="button" className="btn primary sm" onClick={() => void saveArtifact()}>
          Save to file
        </button>
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
