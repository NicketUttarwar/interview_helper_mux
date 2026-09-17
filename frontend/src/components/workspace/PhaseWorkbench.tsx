import { useMemo, useState } from "react";
import { useApp } from "../../context/AppContext";
import { V2_PHASES, isV2Enabled, phaseForStage } from "../../utils/v2Phases";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { StageStepWorkbench } from "./StageStepWorkbench";
import { NlePanel } from "./NlePanel";
import { HomunculusPanel } from "./HomunculusPanel";
import { SolverHaltPanel } from "./SolverHaltPanel";

function phaseStatus(
  phase: (typeof V2_PHASES)[number],
  run: NonNullable<ReturnType<typeof useApp>["run"]>,
): "done" | "active" | "pending" {
  const stageIds = [...phase.stages];
  if (phase.gate) stageIds.push(phase.gate);
  if (stageIds.length === 0) {
    if (phase.id === "start") return run.run_id ? "done" : "active";
    if (phase.nle) return "pending";
    return "pending";
  }
  const statuses = stageIds.map((id) => run.stages.find((s) => s.id === id)?.status ?? "pending");
  if (statuses.every((s) => s === "done")) return "done";
  if (statuses.some((s) => s === "action_required" || s === "awaiting_write_approval")) {
    return "active";
  }
  const nav = resolvePipelineNav(run, { selectedStageId: null, jobRunning: false, apiGrants: {} });
  const current = nav.currentStage?.id ?? nav.nextStage?.id;
  if (current && stageIds.includes(current)) return "active";
  if (phase.gate === current) return "active";
  return statuses.some((s) => s === "done") ? "active" : "pending";
}

export function PhaseWorkbench() {
  const {
    run,
    config,
    selectedStageId,
    selectStage,
    setPipelineSubTab,
    showToast,
    appendClientLog,
    refreshRun,
  } = useApp();
  const [splitBusy, setSplitBusy] = useState(false);

  const activePhase = useMemo(() => {
    if (!run) return V2_PHASES[0];
    if (run.transcript_review_pending) {
      const byG0 = phaseForStage("transcript_review");
      if (byG0) return byG0;
    }
    if (run.gap_framing_decision_pending) {
      const byFraming = phaseForStage("missing_framing") || phaseForStage("framing_posture_decide");
      if (byFraming) return byFraming;
    }
    if (run.meta?.needs_operator && run.meta?.needs_operator_stage) {
      const byOp = phaseForStage(String(run.meta.needs_operator_stage));
      if (byOp) return byOp;
    }
    if (selectedStageId) {
      const byStage = phaseForStage(selectedStageId);
      if (byStage) return byStage;
    }
    for (const phase of V2_PHASES) {
      if (phaseStatus(phase, run) === "active") return phase;
    }
    return V2_PHASES[0];
  }, [run, selectedStageId]);

  const segmentsExist = Boolean(
    run?.stages?.some(
      (s) =>
        ["boundary_detection", "segment_classification", "boundary_topic_resplit"].includes(s.id) &&
        s.status === "done",
    ),
  );

  const splitSelectedHint = async () => {
    setSplitBusy(true);
    try {
      setPipelineSubTab("timeline");
      appendClientLog("Opened timeline for split", "action", "nle", "gui.workbench.split");
      showToast("Timeline open — select a segment and use Split at playhead", "info");
      await refreshRun();
    } catch (err) {
      showToast(String(err), "error");
    } finally {
      setSplitBusy(false);
    }
  };

  if (!run || !isV2Enabled(config)) {
    return <StageStepWorkbench />;
  }

  return (
    <div className="phase-workbench">
      <nav className="phase-workbench-nav" aria-label="Pipeline phases">
        <ol className="phase-workbench-list">
          {V2_PHASES.map((phase, idx) => {
            const status = phaseStatus(phase, run);
            const isActive = phase.id === activePhase.id;
            return (
              <li key={phase.id}>
                <button
                  type="button"
                  className={`phase-workbench-item status-${status}${isActive ? " active" : ""}`}
                  onClick={() => {
                    if (phase.nle) {
                      setPipelineSubTab("timeline");
                      return;
                    }
                    const target =
                      phase.gate ??
                      phase.stages.find((id) => run.stages.find((s) => s.id === id)) ??
                      phase.stages[0];
                    if (target) void selectStage(target);
                  }}
                >
                  <span className="phase-workbench-num">{idx + 1}</span>
                  <span className="phase-workbench-label">{phase.label}</span>
                  {phase.optional ? (
                    <span className="phase-workbench-tag">optional</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ol>
      </nav>
      <div className="phase-workbench-main">
        <header className="phase-workbench-header">
          <h2>{activePhase.label}</h2>
          <p className="hint">{activePhase.description}</p>
          {segmentsExist ? (
            <div className="phase-workbench-split-bar">
              <button
                type="button"
                className="btn sm primary"
                disabled={splitBusy}
                onClick={() => void splitSelectedHint()}
                title="Always available after segments exist — opens timeline and splits at playhead when selected"
              >
                Split segment
              </button>
              <span className="hint">
                Cut long or multi-topic clips (N-way cuts supported in timeline). Auto-splits also run at boundary enrich.
              </span>
            </div>
          ) : null}
        </header>
        {activePhase.nle ? (
          <NlePanel />
        ) : activePhase.id === "start" ? (
          <p className="hint">Select or resume an execution from the Start tab.</p>
        ) : (
          <>
            <HomunculusPanel />
            <SolverHaltPanel />
            <StageStepWorkbench />
          </>
        )}
      </div>
    </div>
  );
}
