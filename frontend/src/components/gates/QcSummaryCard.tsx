import { useApp } from "../../context/AppContext";
import { useAsyncAction } from "../../hooks/useAsyncAction";
import { shouldBlockOperatorActionsForJob } from "../../utils/partialAcceleratedGuard";
import {
  resolveQcDisplayState,
  resolveQcBlocksShip,
  type QcDisplayState,
} from "../../utils/qcSummaryState";

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
    partialAutoGPublish,
  } = useApp();
  const { busy: redoBusy, run: runRedo } = useAsyncAction("redo");
  const jobBlocksUi = shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);
  const summary = run?.meta?.qc_summaries?.[qcKey];
  if (!summary) return null;

  const labels: Record<string, string> = {
    narrative_qc: "Flow 1 narrative QC",
    edl_narrative_qc: "Flow 1 EDL narrative QC",
    show_notes_qc: "Show description QC",
    mix_intelligibility: "Mix intelligibility QC",
    listen_delight: "Listen delight audit",
    post_master_quality: "Post-master quality",
  };
  const label = labels[qcKey] || qcKey;

  const failedDimensions = Array.isArray(summary.failed_dimensions)
    ? (summary.failed_dimensions as unknown[]).map(String)
    : [];
  const overall = typeof summary.overall === "number" ? (summary.overall as number) : null;
  const displayState: QcDisplayState = resolveQcDisplayState(summary);
  const blocksShip = resolveQcBlocksShip(summary, qcKey, run?.meta?.qc_summaries);

  const stateLabel: Record<QcDisplayState, string> = {
    pass: "Pass",
    advisory_fail: "Advisory fail",
    blocking_fail: "Blocking fail",
    waived: "Waived",
  };

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

  const cardClass =
    displayState === "pass"
      ? "qc-pass"
      : displayState === "waived"
        ? "qc-waived"
        : displayState === "advisory_fail"
          ? "qc-advisory"
          : "qc-fail";

  return (
    <div className={`qc-summary-card ${cardClass}`}>
      <h4>{label}</h4>
      <p>
        {stateLabel[displayState]}
        {summary.strict ? " (strict)" : ""}
      </p>
      {Array.isArray(summary.errors) && summary.errors.length ? (
        <ul>
          {summary.errors.slice(0, 4).map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      ) : null}
      {failedDimensions.length ? (
        <ul>
          {failedDimensions.slice(0, 7).map((dim, i) => (
            <li key={i}>Below floor: {dim}</li>
          ))}
        </ul>
      ) : null}
      {overall !== null || blocksShip || displayState !== "pass" ? (
        <p className="hint">
          {overall !== null ? `Overall ${overall.toFixed(2)}` : null}
          {overall !== null ? " — " : ""}
          {blocksShip
            ? "blocks Ship (publish_allowed is false / finalize refuse)."
            : displayState === "waived"
              ? "quality waived — does not alone green Ship without publish_allowed."
              : displayState === "advisory_fail"
                ? "advisory only; does not block Ship."
                : displayState === "blocking_fail"
                  ? "blocking gate."
                  : "does not block Ship."}
        </p>
      ) : null}
      {displayState === "blocking_fail" || displayState === "advisory_fail" ? (
        <p className="hint">
          Fix issues in the activity log or Files tab, then redo from this step and re-run.
        </p>
      ) : null}
      {displayState === "blocking_fail" || displayState === "advisory_fail" ? (
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
              disabled={redoBusy || jobBlocksUi || actionBusy}
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
