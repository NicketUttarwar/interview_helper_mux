import type { HistoryEntry } from "../../../hooks/useNleHistory";

interface Props {
  entries: HistoryEntry[];
  pointer: number;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onRestore: (index: number) => void;
}

export function EditHistoryPanel({
  entries,
  pointer,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onRestore,
}: Props) {
  if (!entries.length) return null;

  return (
    <div className="edit-history-panel">
      <div className="edit-history-head">
        <strong>Edit history</strong>
        <div className="btn-row">
          <button type="button" className="btn sm ghost" disabled={!canUndo} onClick={() => void onUndo()}>
            Undo
          </button>
          <button type="button" className="btn sm ghost" disabled={!canRedo} onClick={() => void onRedo()}>
            Redo
          </button>
        </div>
      </div>
      <ul className="edit-history-list">
        {[...entries].reverse().map((entry) => {
          const idx = entries.indexOf(entry);
          const active = idx === pointer;
          return (
            <li key={entry.id} className={active ? "active" : ""}>
              <span>{entry.label}</span>
              {!active ? (
                <button
                  type="button"
                  className="btn sm ghost"
                  onClick={() => void onRestore(idx)}
                >
                  Restore
                </button>
              ) : (
                <span className="muted">current</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
