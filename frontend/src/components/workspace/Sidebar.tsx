import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { useJourney } from "../../hooks/useJourney";
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
  } = useApp();
  const { phase, runExecuteHint, isBlocked } = useJourney(run);
  const journeyEnabled = config?.journey_ui?.enabled !== false;

  const grouped = useMemo(
    () => (run ? groupStages(run.stages) : new Map()),
    [run?.stages],
  );

  if (!run) return null;

  const blocked = run.stages.some((s) => s.status === "action_required");
  const running = jobRunning;

  const runPhaseCta = () => {
    if (!runExecuteHint) return;
    void executeJob(runExecuteHint.body);
  };

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
        {journeyEnabled && runExecuteHint ? (
          <button
            type="button"
            className="btn primary block"
            disabled={running || isBlocked}
            onClick={runPhaseCta}
          >
            {runExecuteHint.label}
          </button>
        ) : null}
        <button
          type="button"
          className="btn primary block"
          disabled={running || blocked}
          onClick={() => void runNextStage()}
        >
          Run next stage
        </button>
        <button
          type="button"
          className="btn ghost block"
          disabled={running || blocked}
          onClick={() => void executeJob({ mode: "analysis" })}
        >
          Run all analysis
        </button>
        <button
          type="button"
          className="btn danger ghost block"
          onClick={() => void redoFromStage()}
        >
          Redo from selected stage
        </button>
      </div>
    </aside>
  );
}
