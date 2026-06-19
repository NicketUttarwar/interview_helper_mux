import { useApp } from "../../context/AppContext";
import { filterLiveStream, latestEntry } from "../../utils/logStreams";
import { escapeHtml, formatTs } from "../../utils";
import { useGlobalOperatorAction } from "../../hooks/useOperatorAction";
import { stageTitleForId } from "../../utils/checkpoint";
import { useStageProgress } from "../../hooks/useStageProgress";

export function ActivityTeaser() {
  const {
    activeTab,
    logEntries,
    run,
    jobRunning,
    apiGrants,
    selectedStageId,
    setActiveTab,
    setActivityLogCollapsed,
    openActionModal,
    selectStage,
  } = useApp();
  const { activeSubstepGlobal } = useStageProgress();

  const operatorAction = useGlobalOperatorAction(run, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });

  if (activeTab === "pipeline") return null;

  const live = filterLiveStream(logEntries, run, jobRunning);
  const last = latestEntry(live) || latestEntry(logEntries);
  const attentionHeadline =
    operatorAction.mode === "needs_you" ? operatorAction.headline : null;
  const runningTitle =
    jobRunning && run?.job
      ? stageTitleForId(run.stages, run.job.current_stage || run.job.stage)
      : null;

  const goAttention = () => {
    if (operatorAction.mode === "needs_you") {
      if (operatorAction.stageId) void selectStage(operatorAction.stageId);
      openActionModal();
      setActiveTab("pipeline");
      return;
    }
  };

  return (
    <footer
      className={`activity-teaser log-strip${attentionHeadline ? " has-attention" : ""}`}
      data-testid="activity-teaser"
      role="button"
      aria-label={
        attentionHeadline
          ? `Needs attention: ${attentionHeadline}. Open checkpoint.`
          : "Open pipeline activity log"
      }
      aria-live="polite"
      tabIndex={0}
      onClick={() => {
        if (attentionHeadline) {
          goAttention();
          return;
        }
        setActiveTab("pipeline");
        setActivityLogCollapsed(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          if (attentionHeadline) goAttention();
          else {
            setActiveTab("pipeline");
            setActivityLogCollapsed(false);
          }
        }
      }}
    >
      <div className="log-strip-head">
        <span className="log-strip-title">Latest activity</span>
        <span className="log-strip-hint muted">
          {attentionHeadline ? "Go →" : "Open Pipeline activity →"}
        </span>
      </div>
      <div className="log-strip-body">
        {attentionHeadline ? (
          <p className="activity-teaser-attention">{attentionHeadline}</p>
        ) : activeSubstepGlobal ? (
          <p className="muted">{activeSubstepGlobal.label}</p>
        ) : runningTitle ? (
          <p className="muted">Running — {runningTitle}</p>
        ) : !last ? (
          <span className="muted">Activity appears here as the pipeline runs.</span>
        ) : (
          <div className={`log-entry level-${last.level || "info"}`}>
            <span className="log-ts">{formatTs(last.ts)}</span>
            <span className="log-msg">{escapeHtml(last.message)}</span>
          </div>
        )}
      </div>
    </footer>
  );
}
