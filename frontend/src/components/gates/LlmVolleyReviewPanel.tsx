import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatApiError } from "../../utils/safeApi";

/**
 * Optional LLM volley review — message packets (system/user/assistant), not speaker conversation.
 * Default journey does not require this panel (NORTH_STAR). Off unless operator opens it.
 */

type LlmCallIndexRow = {
  stage?: string;
  attempt?: number;
  path?: string;
  task_kind?: string;
};

export function LlmVolleyReviewPanel() {
  const { run, showToast } = useApp();
  const [rows, setRows] = useState<LlmCallIndexRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!run) return;
    setLoading(true);
    // Prefer artifact index when present; fail soft if API missing.
    void api<{ lines?: LlmCallIndexRow[] } | string>(
      `/api/runs/${run.run_id}/artifact?path=${encodeURIComponent("understanding/llm_calls/index.jsonl")}`,
    )
      .then((body) => {
        if (typeof body === "string") {
          const parsed: LlmCallIndexRow[] = [];
          for (const line of body.split("\n")) {
            if (!line.trim()) continue;
            try {
              parsed.push(JSON.parse(line) as LlmCallIndexRow);
            } catch {
              /* skip */
            }
          }
          setRows(parsed.slice(-40));
          return;
        }
        setRows([]);
      })
      .catch((reason) => {
        setRows([]);
        showToast(formatApiError(reason, "LLM volley index (optional)"), "info");
      })
      .finally(() => setLoading(false));
  }, [run, showToast]);

  if (!run) return null;
  return (
    <div className="quality-offer-card" data-action-id="gui.llm_volley.review">
      <h4>LLM volley review</h4>
      <p className="muted sm">
        Optional inspection of stage message packets (system / user / assistant). This is{" "}
        <strong>not</strong> speaker volley (podcast conversation). Default journey does not require
        this surface.
      </p>
      {loading ? <p className="muted sm">Loading…</p> : null}
      {!loading && !rows.length ? (
        <p className="muted sm">No LLM call index yet, or artifact unavailable.</p>
      ) : (
        <ul className="llm-volley-list">
          {rows.map((r, i) => (
            <li key={`${r.stage}-${r.attempt}-${i}`}>
              <code>{r.stage || "?"}</code> attempt {r.attempt ?? "—"}{" "}
              <span className="muted sm">{r.task_kind || ""}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
