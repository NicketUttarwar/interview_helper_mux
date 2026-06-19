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
    setPipelineSubTab,
    setActiveTab,
    runNextStage,
    approveWriteAndContinue,
    acknowledgeHandoff,
    setActiveSubstepId,
  } = useApp();

  if (item.status !== "todo") return null;

  const journeyHint = run?.journey?.execute_hint;
  if (
    item.kind === "checkpoint" &&
    journeyHint?.action === "checkpoint" &&
    (!item.stage_id || journeyHint.stage_id === item.stage_id)
  ) {
    return null;
  }

  const sid = stageId || item.stage_id || run?.stages.find((s) => s.status !== "done")?.id || "";
  const handlers = {
    selectStage: (id: string) => void selectStage(id),
    setActiveTab,
    setPipelineSubTab,
    openActionModal,
    closeActionModal: () => {},
    runNextStage: () => void runNextStage(),
    approveWrite: (id: string) => void approveWriteAndContinue(id),
    acknowledgeHandoff: () => void acknowledgeHandoff(),
    setActiveSubstepId,
  };

  const label = guidanceActionLabel(item.kind || item.action, item.stage_id);

  return (
    <button
      type="button"
      className={className}
      onClick={() => activateGuidanceItem(item, sid, handlers)}
    >
      {label}
    </button>
  );
}
