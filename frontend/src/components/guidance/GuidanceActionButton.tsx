import type { GuidanceItem } from "../../types";
import { useApp } from "../../context/AppContext";

interface Props {
  item: GuidanceItem;
  className?: string;
}

export function GuidanceActionButton({ item, className = "btn ghost sm" }: Props) {
  const { selectStage, openActionModal, setPipelineSubTab, setActiveTab } = useApp();

  if (item.status !== "todo") return null;

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
      case "start":
        setActiveTab("start");
        return;
      default:
        if (item.stage_id) void selectStage(item.stage_id);
        else openActionModal();
    }
  };

  const label =
    item.kind === "profile"
      ? "Open profile"
      : item.kind === "story_board"
        ? "Open Story Board"
        : item.kind === "checkpoint"
          ? "Open checkpoint"
          : item.stage_id
            ? "Go to step"
            : "Open";

  return (
    <button type="button" className={className} onClick={onClick}>
      {label}
    </button>
  );
}
