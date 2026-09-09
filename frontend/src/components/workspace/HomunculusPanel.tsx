import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";

interface GateCategory {
  open?: boolean;
  blocks_analysis?: boolean;
  never_auto?: boolean;
  decision?: string | { action?: string };
}

interface HomunculusStatus {
  homunculus_version?: string;
  active?: boolean;
  budget?: {
    remaining?: Record<string, number>;
    max_invokes_per_identity?: number;
    max_conductor_turns?: number;
  };
  last_fact_ids?: string[];
  admitted_tail?: Array<{ fact_id?: string; action?: string; identity?: string }>;
  issues?: Array<{ issue_id?: string; kind?: string }>;
  limit_exhausted?: { identity?: string; reason?: string } | null;
  memory_fact_count?: number;
  gates?: {
    categories?: string[];
    decisions?: Record<string, { action?: string } | string>;
    [key: string]: unknown;
  };
}

const GATE_LABELS: Record<string, string> = {
  transcript_integrity: "G0 transcript",
  framing_consent: "G-Framing",
  vo_pickup: "G1 VO",
  source_preclean: "Preclean",
  nle_optional: "NLE",
  listen_borderline: "G-Listen",
  optimizer_authority: "Optimizer",
  quality_ship: "Quality / halt",
  publish_package: "G-Publish",
  prompt_promotion: "Prompt stock",
};

export function HomunculusPanel() {
  const { runId, run } = useApp();
  const version = run?.meta?.homunculus_version || "0.0.0";
  const isHomunculus = (run?.meta?.homunculus_kind || "") === "homunculus" || version !== "0.0.0";
  const [status, setStatus] = useState<HomunculusStatus | null>(null);

  useEffect(() => {
    if (!runId || !isHomunculus) {
      setStatus(null);
      return;
    }
    let cancelled = false;
    void api<HomunculusStatus>(`/api/runs/${runId}/homunculus`)
      .then((data) => {
        if (!cancelled) setStatus(data);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, version, isHomunculus, run?.meta?.updated_at]);

  if (!isHomunculus) return null;

  const remaining = status?.budget?.remaining || {};
  const lastIds = status?.last_fact_ids || [];
  const admitted = status?.admitted_tail || [];
  const omitted = admitted
    .map((row) => row.fact_id)
    .filter((id): id is string => typeof id === "string" && id.length > 0 && !lastIds.includes(id));
  const categories = status?.gates?.categories || Object.keys(GATE_LABELS);
  const decisions = status?.gates?.decisions || {};

  return (
    <section className="panel panel-compact" data-testid="homunculus-panel">
      <div className="panel-head">
        <h3>Why this volley</h3>
      </div>
      {status?.limit_exhausted ? (
        <p className="hint" role="alert">
          Limit exhausted: {status.limit_exhausted.identity} ({status.limit_exhausted.reason})
        </p>
      ) : null}
      <p className="hint sm">
        Remaining 3/1 caps shown per identity. Packer selects fact IDs; host renders turns.
      </p>
      <div className="asset-meta">
        Selected facts: {lastIds.length ? lastIds.join(", ") : "(none yet)"}
      </div>
      <div className="asset-meta">
        Omitted but available: {omitted.length ? omitted.slice(0, 8).join(", ") : "(none)"}
      </div>
      <div className="asset-meta">
        Memory facts: {status?.memory_fact_count ?? 0}
        {Object.keys(remaining).length
          ? ` · remaining: ${Object.entries(remaining)
              .slice(0, 6)
              .map(([k, v]) => `${k}:${v}`)
              .join(" ")}`
          : ""}
      </div>
      <div className="panel-head" style={{ marginTop: "0.75rem" }}>
        <h3>Gate categories</h3>
      </div>
      <p className="hint sm">Homunculus controller. G0 cannot skip or auto-resolve.</p>
      <div className="homunculus-gate-grid" data-testid="homunculus-gate-cards">
        {categories.map((id) => {
          const raw = status?.gates?.[id];
          const cat = (raw && typeof raw === "object" ? raw : {}) as GateCategory;
          const stored = decisions[id];
          const action =
            cat.decision && typeof cat.decision === "object"
              ? cat.decision.action
              : typeof cat.decision === "string"
                ? cat.decision
                : typeof stored === "object"
                  ? stored.action
                  : stored;
          const open = Boolean(cat.open);
          return (
            <div
              key={id}
              className={`homunculus-gate-card${open ? " is-open" : ""}`}
              data-gate-category={id}
            >
              <div className="homunculus-gate-title">{GATE_LABELS[id] || id}</div>
              <div className="asset-meta">
                {open ? "open" : "closed"}
                {action ? ` · ${action}` : ""}
                {cat.blocks_analysis ? " · blocks analysis" : ""}
                {cat.never_auto ? " · never auto" : ""}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
