import type { GuidanceItem } from "../../types";
import { useApp } from "../../context/AppContext";
import { guidanceActionLabel } from "../../utils/checkpointLabels";

interface Props {
  item: GuidanceItem;
  className?: string;
}

export function GuidanceActionButton({ item, className = "btn ghost sm" }: Props) {
  const { run, selectStage, openActionModal, setPipelineSubTab, setActiveTab, runNextStage } =
    useApp();

  if (item.status !== "todo") return null;

  const journeyHint = run?.journey?.execute_hint;
  if (
    item.kind === "checkpoint" &&
    journeyHint?.action === "checkpoint" &&
    (!item.stage_id || journeyHint.stage_id === item.stage_id)
  ) {
    return null;
  }

  const onClick = () => {
    switch (item.kind || item.action) {
      case "profile":
      case "story_board":
        setActiveTab("pipeline");
        setPipelineSubTab(item.kind === "profile" ? "profile" : "story");
        if (item.stage_id) void selectStage(item.stage_id);
        return;
      case "checkpoint":
        if (item.stage_id) void selectStage(item.stage_id);
        openActionModal();
        return;
      case "run":
        if (item.stage_id) void selectStage(item.stage_id);
        void runNextStage();
        return;
      case "start":
        setActiveTab("start");
        return;
      default:
        if (item.stage_id) void selectStage(item.stage_id);
        else openActionModal();
    }
  };

  const label = guidanceActionLabel(item.kind || item.action, item.stage_id);

  return (
    <button type="button" className={className} onClick={onClick}>
      {label}
    </button>
  );
}
