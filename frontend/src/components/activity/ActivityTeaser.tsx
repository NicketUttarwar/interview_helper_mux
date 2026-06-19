import { useApp } from "../../context/AppContext";
import { filterLiveStream, latestEntry } from "../../utils/logStreams";
import { escapeHtml, formatTs } from "../../utils";
import { actionSummaryText } from "../../utils/checkpoint";
import { resolvePendingAction } from "../../utils/pendingAction";
import { pendingActionToSubstep } from "../../utils/stageSubsteps";
import { stageTitleForId } from "../../utils/checkpoint";
import { useStageProgress } from "../../hooks/useStageProgress";

export function ActivityTeaser() {
  const {
    activeTab,
    logEntries,
    run,
    jobRunning,
    apiGrants,
    setActiveTab,
    setActivityLogCollapsed,
    activateSubstep,
  } = useApp();
  const { activeSubstepGlobal } = useStageProgress();

  if (activeTab === "pipeline") return null;

  const live = filterLiveStream(logEntries, run, jobRunning);
  const last = latestEntry(live) || latestEntry(logEntries);
  const summary = actionSummaryText(run, apiGrants);
  const pending = resolvePendingAction(run, apiGrants);
  const runningTitle =
    jobRunning && run?.job
      ? stageTitleForId(run.stages, run.job.current_stage || run.job.stage)
      : null;

  const goAttention = () => {
    if (!pending) return;
    activateSubstep(pendingActionToSubstep(pending));
  };

  return (
    <footer
      className={`activity-teaser log-strip${summary ? " has-attention" : ""}`}
      data-testid="activity-teaser"
      role="log"
      aria-live="polite"
      tabIndex={0}
      onClick={() => {
        if (pending) {
          goAttention();
          return;
        }
        setActiveTab("pipeline");
        setActivityLogCollapsed(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          if (pending) goAttention();
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
          {pending ? "Go →" : "Open Pipeline activity →"}
        </span>
      </div>
      <div className="log-strip-body">
        {summary ? (
          <p className="activity-teaser-attention">{summary}</p>
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
