import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { resolvePrecleanOffer } from "../../utils/preclean";
import {
  resolveStagePrimaryAction,
  type StagePrimaryActionSpec,
} from "../../utils/stagePrimaryAction";
import type { StageInfo } from "../../types";

interface Props {
  stage: StageInfo;
  compact?: boolean;
}

function actionButtonClass(spec: StagePrimaryActionSpec, compact?: boolean): string {
  const base = compact ? "btn sm" : "btn";
  if (spec.disabled || spec.kind === "none" || spec.kind === "waiting") {
    return `${base} ghost stage-primary-btn`;
  }
  if (spec.kind === "run" || spec.kind === "handoff") {
    return `${base} primary stage-primary-btn`;
  }
  return `${base} primary stage-primary-btn`;
}

export function StagePrimaryAction({ stage, compact }: Props) {
  const {
    run,
    selectedStageId,
    jobRunning,
    apiGrants,
    sessionReady,
    selectStage,
    openActionModal,
    acknowledgeHandoff,
    executeJob,
    runNextStage,
  } = useApp();

  const nav = useMemo(
    () =>
      resolvePipelineNav(run, {
        selectedStageId,
        jobRunning,
        apiGrants,
      }),
    [run, selectedStageId, jobRunning, apiGrants],
  );

  const spec = useMemo(() => {
    if (!run) return null;
    const offer = resolvePrecleanOffer(stage, run.meta);
    return resolveStagePrimaryAction(stage, run, nav, {
      jobRunning,
      hasPrecleanOffer: Boolean(offer),
    });
  }, [run, stage, nav, jobRunning]);

  if (!spec || spec.kind === "none") return null;

  const onClick = () => {
    if (spec.disabled) return;
    switch (spec.kind) {
      case "run":
        if (spec.targetStageId && spec.targetStageId !== stage.id) {
          void selectStage(spec.targetStageId).then(() => {
            if (spec.runStageId && spec.runStageId === nav.nextStage?.id) {
              void runNextStage();
            } else if (spec.runStageId) {
              void executeJob({ mode: "stage", stage: spec.runStageId });
            }
          });
          return;
        }
        if (spec.runStageId === nav.nextStage?.id) {
          void runNextStage();
        } else if (spec.runStageId) {
          void executeJob({ mode: "stage", stage: spec.runStageId });
        } else {
          void runNextStage();
        }
        return;
      case "checkpoint":
        if (spec.targetStageId) void selectStage(spec.targetStageId);
        openActionModal();
        return;
      case "handoff":
        void acknowledgeHandoff();
        return;
      case "navigate":
        if (spec.targetStageId) void selectStage(spec.targetStageId);
        return;
      default:
        return;
    }
  };

  const showButton =
    spec.kind === "run" ||
    spec.kind === "checkpoint" ||
    spec.kind === "handoff" ||
    spec.kind === "navigate";

  return (
    <div
      className={`stage-primary-action${compact ? " compact" : ""}${spec.kind === "waiting" ? " waiting" : ""}`}
      data-testid="stage-primary-action"
    >
      <div className="stage-primary-action-copy">
        <p className="stage-primary-action-eyebrow">Next action</p>
        {showButton ? (
          <button
            type="button"
            className={actionButtonClass(spec, compact)}
            disabled={spec.disabled || !sessionReady}
            data-testid="stage-primary-action-btn"
            onClick={onClick}
          >
            {spec.label}
          </button>
        ) : (
          <p className="stage-primary-action-label">{spec.label}</p>
        )}
        {spec.sublabel ? (
          <p className="hint stage-primary-action-sublabel">{spec.sublabel}</p>
        ) : null}
      </div>
    </div>
  );
}
