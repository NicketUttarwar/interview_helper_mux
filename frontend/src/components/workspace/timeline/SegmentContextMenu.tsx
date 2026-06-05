interface MenuAction {
  id: string;
  label: string;
  disabled?: boolean;
}

interface Props {
  x: number;
  y: number;
  segmentId: string;
  onAction: (actionId: string) => void;
  onClose: () => void;
}

const ACTIONS: MenuAction[] = [
  { id: "exclude", label: "Exclude" },
  { id: "restore", label: "Restore" },
  { id: "mark_redo", label: "Mark redo" },
  { id: "snap_trim", label: "Snap trim" },
  { id: "tighten", label: "Tighten pauses" },
  { id: "split", label: "Split at playhead" },
  { id: "silence_trim", label: "Trim silence" },
];

export function SegmentContextMenu({ x, y, segmentId, onAction, onClose }: Props) {
  return (
    <>
      <div className="segment-context-backdrop" onClick={onClose} />
      <div
        className="segment-context-menu"
        style={{ left: x, top: y }}
        role="menu"
      >
        <p className="segment-context-title">{segmentId}</p>
        {ACTIONS.map((a) => (
          <button
            key={a.id}
            type="button"
            className="segment-context-item"
            disabled={a.disabled}
            onClick={() => {
              onAction(a.id);
              onClose();
            }}
          >
            {a.label}
          </button>
        ))}
      </div>
    </>
  );
}
