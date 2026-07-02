import { useCallback, useEffect, useState } from "react";
import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import type { VoLine } from "../../types";
import { formatApiError } from "../../utils/safeApi";
import { traceAction } from "../../operator/traceAction";

export function ConversationStudioPanel() {
  const { runId, refreshRun, showToast } = useApp();
  const [lines, setLines] = useState<VoLine[]>([]);
  const [newText, setNewText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await api<{ lines: VoLine[] }>(`/api/runs/${runId}/gap-report/lines`);
      setLines(res.lines || []);
    } catch {
      setLines([]);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const addLine = async () => {
    if (!runId || !newText.trim() || busy) return;
    setBusy(true);
    traceAction("gui.gap_report.add_line", "Adding pickup line from studio", {
      stage: "optimal_questions",
    });
    try {
      await api(`/api/runs/${runId}/gap-report/lines`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: newText.trim(), gap_type: "reaction_line" }),
      });
      setNewText("");
      showToast("Pickup line added.");
      await load();
      await refreshRun();
    } catch (e) {
      showToast(formatApiError(e, "Add line"), "error");
    } finally {
      setBusy(false);
    }
  };

  const removeLine = async (lineId: string) => {
    if (!runId || busy) return;
    setBusy(true);
    try {
      await api(`/api/runs/${runId}/gap-report/lines/${lineId}`, { method: "DELETE" });
      showToast(`Removed ${lineId}`);
      await load();
      await refreshRun();
    } catch (e) {
      showToast(formatApiError(e, "Remove line"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="conversation-studio panel-inset">
      <h4>Conversation studio</h4>
      <p className="hint sm">Add or remove pickup lines (gap pickup speaker only).</p>
      <ul>
        {lines.map((ln) => (
          <li key={ln.line_id}>
            <strong>{ln.line_id}</strong>: {ln.text}
            {ln.post_preview ? " · post-preview" : ""}
            <button
              type="button"
              className="btn ghost sm"
              disabled={busy}
              onClick={() => void removeLine(ln.line_id)}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      <label className="field">
        New pickup line
        <input value={newText} onChange={(e) => setNewText(e.target.value)} />
      </label>
      <button type="button" className="btn sm" disabled={busy || !newText.trim()} onClick={() => void addLine()}>
        Add line
      </button>
    </section>
  );
}
