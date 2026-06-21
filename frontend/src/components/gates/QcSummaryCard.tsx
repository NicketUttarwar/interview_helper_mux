import { useApp } from "../../context/AppContext";

export function QcSummaryCard({
  qcKey,
  stageId,
}: {
  qcKey: string;
  stageId?: string;
}) {
  const {
    run,
    setActiveTab,
    setPipelineSubTab,
    setActivityLogTab,
    setLogFilterPreset,
    selectStage,
    redoFromStage,
  } = useApp();
  const summary = run?.meta?.qc_summaries?.[qcKey];
  if (!summary) return null;

  const labels: Record<string, string> = {
    narrative_qc: "Flow 1 narrative QC",
    edl_narrative_qc: "Flow 1 EDL narrative QC",
    show_description_qc: "Show description QC",
    mix_intelligibility: "Mix intelligibility QC",
  };
  const label = labels[qcKey] || qcKey;

  const openActivity = () => {
    setActiveTab("pipeline");
    setPipelineSubTab("stage");
    setActivityLogTab("live");
  };

  const openErrors = () => {
    setLogFilterPreset({ level: "error", stream: "all", scrollToError: true });
    setActiveTab("logs");
  };

  const redoStep = async () => {
    if (stageId) await selectStage(stageId);
    await redoFromStage();
  };

  return (
    <div className={`qc-summary-card ${summary.passed ? "qc-pass" : "qc-fail"}`}>
      <h4>{label}</h4>
      <p>
        {summary.passed ? "Pass" : "Fail"}
        {summary.strict ? " (strict)" : ""}
      </p>
      {Array.isArray(summary.errors) && summary.errors.length ? (
        <ul>
          {summary.errors.slice(0, 4).map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      ) : null}
      {!summary.passed ? (
        <p className="hint">
          Fix issues in the activity log or Files tab, then redo from this step and re-run.
        </p>
      ) : null}
      {!summary.passed ? (
        <div className="stage-audio-actions flow-choice">
          <button type="button" className="btn ghost sm" onClick={openActivity}>
            View activity
          </button>
          <button type="button" className="btn ghost sm" onClick={openErrors}>
            View errors
          </button>
          <button type="button" className="btn ghost sm" onClick={() => setActiveTab("logs")}>
            View Logs
          </button>
          {stageId ? (
            <button type="button" className="btn primary sm" onClick={() => void redoStep()}>
              Redo from this step
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
