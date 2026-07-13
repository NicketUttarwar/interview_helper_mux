import { useApp } from "../../context/AppContext";
import { useAsyncAction } from "../../hooks/useAsyncAction";

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
    showToast,
    jobRunning,
    actionBusy,
  } = useApp();
  const { busy: redoBusy, run: runRedo } = useAsyncAction("redo");
  const summary = run?.meta?.qc_summaries?.[qcKey];
  if (!summary) return null;

  const labels: Record<string, string> = {
    narrative_qc: "Flow 1 narrative QC",
    edl_narrative_qc: "Flow 1 EDL narrative QC",
    show_notes_qc: "Show description QC",
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

  const redoStep = () =>
    void runRedo(
      async () => {
        if (stageId) await selectStage(stageId);
        await redoFromStage();
      },
      {
        showToast,
        startMessage: `Redoing from ${label}…`,
        successMessage: "Stage reset — run the step again when ready.",
      },
    );

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
            <button
              type="button"
              className="btn primary sm"
              disabled={redoBusy || jobRunning || actionBusy}
              onClick={redoStep}
            >
              {redoBusy ? (
                <>
                  <span className="spinner-inline" aria-hidden /> Resetting…
                </>
              ) : (
                "Redo from this step"
              )}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
