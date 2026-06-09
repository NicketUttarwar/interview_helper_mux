import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { validateArtifactWrite } from "../../schemas/validateArtifact";
import { isJsonArtifactPath } from "../../utils";
import type { StageInfo } from "../../types";

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
  const { run, runId, refreshRun, runNextStage, showToast, closeActionModal } = useApp();
  const [paths, setPaths] = useState<string[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [editorValue, setEditorValue] = useState("");
  const [isJson, setIsJson] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const stageId = run?.job?.pending_write_stage || run?.job?.stage || stage.id;

  const loadPaths = useCallback(async () => {
    if (!runId) return;
    try {
      const data = await api<{ paths?: string[] }>(
        `/api/runs/${runId}/pending-writes/${stageId}`,
      );
      const p = data.paths || [];
      setPaths(p);
      setSelectedPath((prev) => (prev && p.includes(prev) ? prev : p[0] || ""));
    } catch {
      setPaths([]);
      setSelectedPath("");
    }
  }, [runId, stageId]);

  useEffect(() => {
    void loadPaths();
  }, [loadPaths]);

  const loadContent = useCallback(
    async (path: string) => {
      if (!runId || !path) return;
      setIsJson(isJsonArtifactPath(path));
      try {
        const data = await api<Record<string, unknown> | { text?: string }>(
          `/api/runs/${runId}/pending-writes/${stageId}/content?path=${encodeURIComponent(path)}`,
        );
        if (isJsonArtifactPath(path)) {
          setEditorValue(JSON.stringify(data, null, 2));
        } else {
          setEditorValue((data as { text?: string }).text ?? "");
        }
      } catch {
        setEditorValue("");
      }
    },
    [runId, stageId],
  );

  useEffect(() => {
    if (selectedPath && fileKind(selectedPath) !== "audio") void loadContent(selectedPath);
  }, [selectedPath, loadContent]);

  const saveEdit = async () => {
    if (!runId || !selectedPath) return;
    try {
      if (isJson) {
        const parsed = JSON.parse(editorValue) as Record<string, unknown>;
        const v = validateArtifactWrite(selectedPath, parsed);
        if (!v.ok) {
          showToast(`Validation: ${v.errors[0]}`);
          return;
        }
        await api(`/api/runs/${runId}/pending-writes/${stageId}/content`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: selectedPath, data: parsed }),
        });
      } else {
        await api(`/api/runs/${runId}/pending-writes/${stageId}/content`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: selectedPath, text: editorValue }),
        });
      }
      showToast(`Updated ${selectedPath}`);
    } catch (e) {
      showToast(e instanceof ApiError ? e.message : "Save failed");
    }
  };

  const approve = async () => {
    if (!runId || submitting) return;
    setSubmitting(true);
    try {
      await api(`/api/runs/${runId}/pending-writes/${stageId}/approve`, {
        method: "POST",
      });
      showToast("Outputs saved — continuing.");
      closeActionModal();
      await refreshRun();
      await runNextStage();
    } catch (e) {
      showToast(e instanceof ApiError ? e.message : "Approve failed");
    } finally {
      setSubmitting(false);
    }
  };

  const discard = async () => {
    if (!runId || submitting) return;
    setSubmitting(true);
    try {
      await api(`/api/runs/${runId}/pending-writes/${stageId}/discard`, {
        method: "POST",
      });
      showToast("Discarded staged outputs — re-run this step when ready.");
      closeActionModal();
      await refreshRun();
    } catch (e) {
      showToast(e instanceof ApiError ? e.message : "Discard failed");
    } finally {
      setSubmitting(false);
    }
  };

  if (!paths.length) return null;

  return (
    <section className="write-approval-panel panel-inset" aria-label="Review outputs before saving">
      <h3 className="stage-outputs-title">Review outputs before saving</h3>
      <p className="hint">
        <strong>{stage.title}</strong> staged {paths.length} file{paths.length === 1 ? "" : "s"}.
        Preview, edit if needed, then save to disk.
      </p>

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
              <textarea
                className="artifact-editor-textarea"
                value={editorValue}
                onChange={(e) => setEditorValue(e.target.value)}
                rows={14}
              />
              <button type="button" className="btn ghost sm" onClick={() => void saveEdit()}>
                Save edit to staging
              </button>
            </div>
          ) : (
            <p className="hint empty-state">Select a file to preview.</p>
          )}
        </div>
      </div>

      <div className="write-approval-actions">
        <button
          type="button"
          className="btn primary"
          disabled={submitting}
          onClick={() => void approve()}
        >
          Save &amp; continue
        </button>
        <button
          type="button"
          className="btn ghost sm"
          disabled={submitting}
          onClick={() => void discard()}
        >
          Discard &amp; re-run
        </button>
      </div>
    </section>
  );
}
