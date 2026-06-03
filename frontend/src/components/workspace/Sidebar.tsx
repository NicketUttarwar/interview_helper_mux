import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { useJourney } from "../../hooks/useJourney";
import { findHandoffStage } from "../../utils/checkpoint";
import { stageDotClass } from "../../utils/preclean";
import type { OperatorPhase, StageInfo } from "../../types";

const PHASE_ORDER: OperatorPhase[] = [
  "prepare",
  "understand",
  "complete",
  "create",
  "polish",
  "ship",
];

const PHASE_TITLES: Record<OperatorPhase, string> = {
  prepare: "Prepare",
  understand: "Understand",
  complete: "Complete",
  create: "Create",
  polish: "Polish",
  ship: "Ship",
};

function groupStages(stages: StageInfo[]): Map<OperatorPhase, StageInfo[]> {
  const map = new Map<OperatorPhase, StageInfo[]>();
  for (const p of PHASE_ORDER) map.set(p, []);
  for (const s of stages) {
    const op = (s.operator_phase ?? s.phase ?? "understand") as OperatorPhase;
    const key = PHASE_ORDER.includes(op) ? op : "understand";
    map.get(key)!.push(s);
  }
  return map;
}

export function Sidebar() {
  const {
    run,
    selectedStageId,
    selectStage,
    runNextStage,
    executeJob,
    redoFromStage,
    jobRunning,
    config,
    openActionModal,
  } = useApp();
  const { phase, runExecuteHint, isBlocked, blocking } = useJourney(run);
  const journeyEnabled = config?.journey_ui?.enabled !== false;

  const grouped = useMemo(
    () => (run ? groupStages(run.stages) : new Map()),
    [run?.stages],
  );

  if (!run) return null;

  const handoffPending = Boolean(findHandoffStage(run));
  const actionRequired = run.stages.some((s) => s.status === "action_required");
  const needsOperator =
    actionRequired || handoffPending || isBlocked;
  const running = jobRunning;

  const openCheckpoint = () => {
    const target =
      run.stages.find((s) => s.status === "action_required") ||
      (blocking?.stage_id
        ? run.stages.find((s) => s.id === blocking.stage_id)
        : undefined);
    if (target) void selectStage(target.id);
    openActionModal();
  };

  const runPhaseCta = () => {
    if (needsOperator) {
      openCheckpoint();
      return;
    }
    if (!runExecuteHint) return;
    void executeJob(runExecuteHint.body);
  };

  const sidebarHint = running
    ? "Pipeline is running — wait for it to finish or check Logs."
    : needsOperator
      ? blocking?.message ||
        (handoffPending
          ? "Review custom run outputs and acknowledge before the next stage."
          : "Complete the open checkpoint before running more stages.")
      : null;

  const primaryLabel = running
    ? "Running…"
    : needsOperator
      ? "Open required step"
      : runExecuteHint?.label || null;

  return (
    <aside className="sidebar panel">
      <h3>Pipeline</h3>
      <p className="input-label">{run.meta?.input_audio_path || ""}</p>
      {journeyEnabled ? (
        <div className="stage-list-grouped">
          {PHASE_ORDER.map((p) => {
            const items = grouped.get(p) ?? [];
            if (items.length === 0) return null;
            return (
              <section
                key={p}
                className={`stage-phase-group${p === phase ? " current-phase" : ""}`}
              >
                <h4 className="stage-phase-heading">{PHASE_TITLES[p]}</h4>
                <ol className="stage-list">
                  {items.map((s: StageInfo) => (
                    <li
                      key={s.id}
                      className={s.id === selectedStageId ? "active" : ""}
                      onClick={() => void selectStage(s.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void selectStage(s.id);
                      }}
                      role="button"
                      tabIndex={0}
                    >
                      <span className={`stage-dot ${stageDotClass(s.status)}`} />
                      <span>{s.title}</span>
                    </li>
                  ))}
                </ol>
              </section>
            );
          })}
        </div>
      ) : (
        <ol className="stage-list">
          {run.stages.map((s: StageInfo) => (
            <li
              key={s.id}
              className={s.id === selectedStageId ? "active" : ""}
              onClick={() => void selectStage(s.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void selectStage(s.id);
              }}
              role="button"
              tabIndex={0}
            >
              <span className={`stage-dot ${stageDotClass(s.status)}`} />
              <span>{s.title}</span>
            </li>
          ))}
        </ol>
      )}
      <div className="sidebar-actions">
        {journeyEnabled && primaryLabel ? (
          <button
            type="button"
            className="btn primary block"
            disabled={running}
            onClick={runPhaseCta}
          >
            {primaryLabel}
          </button>
        ) : null}
        <button
          type="button"
          className="btn primary block"
          disabled={running}
          onClick={() => {
            if (needsOperator) openCheckpoint();
            else void runNextStage();
          }}
        >
          {needsOperator ? "Continue checkpoint" : "Run next stage"}
        </button>
        <button
          type="button"
          className="btn ghost block"
          disabled={running || actionRequired}
          title={
            actionRequired
              ? "Finish the open checkpoint first"
              : "Run all pending analysis stages"
          }
          onClick={() => void executeJob({ mode: "analysis" })}
        >
          Run all analysis
        </button>
        <button
          type="button"
          className="btn danger ghost block"
          disabled={running}
          onClick={() => void redoFromStage()}
        >
          Redo from selected stage
        </button>
        {sidebarHint ? <p className="sidebar-hint hint">{sidebarHint}</p> : null}
      </div>
    </aside>
  );
}
