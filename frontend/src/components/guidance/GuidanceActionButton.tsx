import type { GuidanceItem } from "../../types";
import { useApp } from "../../context/AppContext";
import { guidanceActionLabel } from "../../utils/checkpointLabels";
import { activateGuidanceItem } from "../../utils/activateSubstep";

interface Props {
  item: GuidanceItem;
  className?: string;
  stageId?: string;
}

export function GuidanceActionButton({ item, className = "btn ghost sm", stageId }: Props) {
  const {
    run,
    selectStage,
    openActionModal,
    closeActionModal,
    setPipelineSubTab,
    setActiveTab,
    runNextStage,
    executeJob,
    approveWriteAndContinue,
    acknowledgeHandoff,
    setActiveSubstepId,
    setActivityLogCollapsed,
    setActivityLogTab,
    showToast,
    skipOptionalStage,
    jobRunning,
    actionBusy,
  } = useApp();

  if (item.status !== "todo") return null;

  const sid = stageId || item.stage_id || run?.stages.find((s) => s.status !== "done")?.id || "";
  const handlers = {
    selectStage: (id: string) => void selectStage(id),
    setActiveTab,
    setPipelineSubTab,
    openActionModal,
    closeActionModal,
    runNextStage: () => void runNextStage(),
    executeStage: (id: string) =>
      void executeJob({ mode: "stage", stage: id }),
    approveWrite: (id: string) => void approveWriteAndContinue(id),
    acknowledgeHandoff: () => void acknowledgeHandoff(),
    setActiveSubstepId,
    setActivityLogCollapsed,
    setActivityLogTab,
    showToast,
    skipOptionalStage: (id: string) => void skipOptionalStage(id),
  };

  const label = guidanceActionLabel(item.kind || item.action, item.stage_id);
  const busy = jobRunning || actionBusy;

  return (
    <button
      type="button"
      className={className}
      disabled={busy}
      onClick={() =>
        activateGuidanceItem(item, sid, handlers, {
          openModal: item.kind === "checkpoint" || item.kind === "action",
        })
      }
    >
      {label}
    </button>
  );
}
