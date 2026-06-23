import { ActivityLogPanel } from "./ActivityLogPanel";

type Props = {
  onDump: () => void;
};

export function GlobalActivityDock({ onDump }: Props) {
  return (
    <div className="global-activity-dock">
      <ActivityLogPanel variant="global" onDumpLast={onDump} />
    </div>
  );
}
