import { useApp } from "../../context/AppContext";
import { stageDotClass } from "../../utils/preclean";

export function Sidebar() {
  const {
    run,
    selectedStageId,
    selectStage,
    runNextStage,
    executeJob,
    redoFromStage,
    jobRunning,
  } = useApp();

  if (!run) return null;

  const blocked = run.stages.some((s) => s.status === "action_required");
  const running = jobRunning;

  return (
    <aside className="sidebar panel">
      <h3>Pipeline</h3>
      <p className="input-label">{run.meta?.input_audio_path || ""}</p>
      <ol className="stage-list">
        {run.stages.map((s) => (
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
      <div className="sidebar-actions">
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
