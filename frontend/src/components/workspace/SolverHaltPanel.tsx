import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { isExpectedEmptyApiError, formatApiError } from "../../utils/safeApi";
import {
  buildSolverPanelModel,
  type BlockedGroup,
  type DeferredStage,
  type SolverDecisionView,
  type SolverPanelModel,
} from "../../utils/solverDecision";

const STAGE_CHIP_LIMIT = 8;

function StageChips({ stages }: { stages: string[] }) {
  const shown = stages.slice(0, STAGE_CHIP_LIMIT);
  const rest = stages.length - shown.length;
  return (
    <div className="solver-halt-chips">
      {shown.map((stage) => (
        <span key={stage} className="solver-halt-chip">
          {stage}
        </span>
      ))}
      {rest > 0 ? <span className="solver-halt-chip more">+{rest} more</span> : null}
    </div>
  );
}

function BlockerRow({ group }: { group: BlockedGroup }) {
  return (
    <li className={`solver-halt-blocker kind-${group.kind}`}>
      <div className="solver-halt-blocker-head">
        <strong>{group.headline}</strong>
        <span className="badge warn">{group.stages.length} blocked</span>
      </div>
      {group.detail ? <p className="hint sm">{group.detail}</p> : null}
      <p className="asset-meta">
        {group.producer
          ? `Satisfied by: ${group.producer}${group.artifact ? ` → ${group.artifact}` : ""}`
          : group.artifact
            ? `No producer declared for ${group.artifact}`
            : "Run-level condition — no producer stage to run"}
      </p>
      <StageChips stages={group.stages} />
      <code className="solver-halt-reason">{group.reason}</code>
    </li>
  );
}

function DeferredSection({ deferred }: { deferred: DeferredStage[] }) {
  if (!deferred.length) return null;
  return (
    <details className="solver-halt-deferred">
      <summary>
        Solver has no opinion on {deferred.length} stage{deferred.length === 1 ? "" : "s"} — not
        blocked
      </summary>
      <p className="hint sm">
        A deferral is the solver declining to decide, usually because the stage contract declares
        no hard inputs. These stages are not waiting on anything the solver can name; the walk
        decides when they run.
      </p>
      <ul className="solver-halt-deferred-list">
        {deferred.map((item) => (
          <li key={item.stage}>
            <span className="solver-halt-chip">{item.stage}</span>
            <span className="hint sm"> {item.why}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function SeveredSection({ model }: { model: SolverPanelModel }) {
  const severed = model.severed;
  if (!severed) return null;
  return (
    <div className="solver-halt-severed" role="alert">
      <strong>Ship path proven unreachable</strong>
      <p className="hint sm">{severed.reason}</p>
      <ul className="solver-halt-unmet-list">
        {severed.unmet.map((unmet) => (
          <li key={`${unmet.artifact}:${unmet.requiredBy}`}>
            <code>{unmet.artifact}</code> required by {unmet.requiredBy || "the ship path"}
            {unmet.producer ? ` · produced by ${unmet.producer}` : " · no producer declared"}
            {unmet.blocker ? ` · ${unmet.blocker}` : ""}
          </li>
        ))}
      </ul>
      {severed.resume ? (
        <p className="asset-meta">Resume from: {severed.resume}</p>
      ) : null}
    </div>
  );
}

function Headline({ model }: { model: SolverPanelModel }) {
  if (model.state === "halted") {
    return (
      <p className="solver-halt-verdict blocked" role="alert">
        Nothing is runnable — {model.blockedGroups.length} distinct blocker
        {model.blockedGroups.length === 1 ? "" : "s"} across {model.blocked.length} stage
        {model.blocked.length === 1 ? "" : "s"}.
      </p>
    );
  }
  if (model.state === "complete") {
    return (
      <p className="solver-halt-verdict">
        Every dispatchable stage is done — nothing left to run.
      </p>
    );
  }
  return (
    <p className="solver-halt-verdict">
      {model.runnable.length} stage{model.runnable.length === 1 ? "" : "s"} runnable
      {model.wouldChoose ? ` · would choose ${model.wouldChoose}` : ""}
      {model.wouldChooseConfident && model.wouldChooseConfident !== model.wouldChoose
        ? ` (first provable: ${model.wouldChooseConfident})`
        : ""}
      .
    </p>
  );
}

/**
 * "Why is nothing runnable" (plan §10.2).
 *
 * Shadow-only telemetry, so the absent-log case is the normal case: it renders as "no
 * solver data yet", never as a halt. Blocked and deferred are kept visually separate —
 * a deferral means the solver has no opinion, not that the stage is waiting on anything.
 */
export function SolverHaltPanel() {
  const { runId } = useApp();
  const [model, setModel] = useState<SolverPanelModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(
    async (signal?: { cancelled: boolean }) => {
      if (!runId) {
        setModel(null);
        return;
      }
      setLoading(true);
      try {
        const view = await api<SolverDecisionView>(`/api/runs/${runId}/solver-decision`);
        if (signal?.cancelled) return;
        setModel(buildSolverPanelModel(view));
        setError(null);
      } catch (err) {
        if (signal?.cancelled) return;
        setModel(null);
        // A run without solver telemetry is the expected state, not a failure to report.
        setError(isExpectedEmptyApiError(err) ? null : formatApiError(err, "Solver decision"));
      } finally {
        if (!signal?.cancelled) setLoading(false);
      }
    },
    [runId],
  );

  useEffect(() => {
    const signal = { cancelled: false };
    void load(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [load]);

  if (!runId) return null;

  const state = model?.state ?? "no_data";

  return (
    <section
      className="panel panel-compact solver-halt-panel"
      data-testid="solver-halt-panel"
      data-solver-state={state}
    >
      <div className="panel-head">
        {/* The alarming title belongs to the halt case only. */}
        <h3>{state === "halted" ? "Why is nothing runnable?" : "Solver view (shadow)"}</h3>
        <button
          type="button"
          className="btn ghost sm"
          disabled={loading}
          onClick={() => void load()}
        >
          {loading ? "Checking…" : "Refresh"}
        </button>
      </div>

      {error ? (
        <p className="hint sm" role="status">
          {error} — the deterministic solver is read-only, so this does not affect the run.
        </p>
      ) : null}

      {!model || model.state === "no_data" ? (
        <p className="hint sm" data-testid="solver-halt-no-data">
          No solver data yet. The deterministic solver is shadow-only and nothing has written{" "}
          <code>{model?.artifact ?? "operator/solver_decision.jsonl"}</code> for this run
          {model?.shadowLogging === false ? " (shadow logging is off)" : ""}. An empty log says
          nothing about runnability — it is the normal state today.
        </p>
      ) : (
        <>
          <Headline model={model} />
          <SeveredSection model={model} />
          {model.blockedGroups.length ? (
            <ul className="solver-halt-blocker-list">
              {model.blockedGroups.map((group) => (
                <BlockerRow key={group.reason} group={group} />
              ))}
            </ul>
          ) : model.state === "halted" ? (
            <p className="hint sm">
              No stage reported a blocking reason. Nothing is dispatchable for a run-level reason —
              check the lease and open gates below.
            </p>
          ) : null}
          <DeferredSection deferred={model.deferred} />
          <div className="asset-meta">
            {model.posture ? `Posture: ${model.posture}` : "Posture unknown"}
            {model.leaseOk === false ? " · run lease held by the GUI" : ""}
            {model.seedFirstIncomplete
              ? ` · first incomplete in seed order: ${model.seedFirstIncomplete}`
              : ""}
          </div>
        </>
      )}

      <div className="asset-meta">
        {model?.source === "live"
          ? "Live evaluation"
          : model?.source === "logged"
            ? "Newest logged decision"
            : "No decision row"}
        {model?.at ? ` · ${model.at}` : ""}
        {` · ${model?.loggedRowCount ?? 0} logged row${(model?.loggedRowCount ?? 0) === 1 ? "" : "s"}`}
        {model?.shadowOnly === false ? " · authoritative" : " · shadow-only, decides nothing"}
      </div>
    </section>
  );
}
