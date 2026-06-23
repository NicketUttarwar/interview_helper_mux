import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../../context/AppContext";
import {
  dedupeConsecutiveLogEntries,
  excludePinnedEntries,
  filterByStage,
  filterErrors,
  filterLiveStream,
  filterWarnings,
  resolveActiveStream,
  resolveFocusStageId,
  resolveLiveStageId,
} from "../../utils/logStreams";
import { LogEntryList } from "./LogEntryList";
import { useStageProgress } from "../../hooks/useStageProgress";
import type { LogStreamTab } from "../../types";

export function ActivityLogPanel({
  variant = "pipeline",
  onDumpLast,
}: {
  variant?: "pipeline" | "global";
  onDumpLast?: () => void;
} = {}) {
  const {
    run,
    logEntries,
    jobRunning,
    selectedStageId,
    pipelineSubTab,
    activityLogTab,
    setActivityLogTab,
    activityLogCollapsed,
    setActivityLogCollapsed,
    setLogFilterPreset,
    setActiveTab,
  } = useApp();

  const { activeSubstep } = useStageProgress(selectedStageId);

  const toolView = pipelineSubTab !== "stage";

  const [autoScroll, setAutoScroll] = useState(true);
  const [liveSeenTs, setLiveSeenTs] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const userScrolledRef = useRef(false);
  const userPinnedActivityTabRef = useRef(false);
  const prevJobRunningRef = useRef(jobRunning);

  const activeStream = useMemo(
    () => resolveActiveStream(run, jobRunning, logEntries),
    [run, jobRunning, logEntries],
  );

  const liveNewCount = useMemo(() => {
    if (activityLogTab !== "live") return 0;
    const live = filterLiveStream(logEntries, run, jobRunning);
    const last = live[live.length - 1];
    if (!last || !liveSeenTs) return live.length > 0 ? 1 : 0;
    return live.filter((e) => e.ts > liveSeenTs).length;
  }, [logEntries, run, jobRunning, activityLogTab, liveSeenTs]);

  const displayed = useMemo(() => {
    if (activityLogTab === "live") {
      return filterLiveStream(logEntries, run, jobRunning);
    }
    if (activityLogTab === "step") {
      return filterByStage(logEntries, selectedStageId);
    }
    return logEntries;
  }, [activityLogTab, logEntries, run, jobRunning, selectedStageId]);

  const pinnedErrors = useMemo(() => {
    if (activityLogTab === "all") return [];
    const errors = filterErrors(logEntries).slice(-5);
    if (activityLogTab === "step") {
      return filterByStage(errors, selectedStageId).slice(-3);
    }
    if (activityLogTab === "live") {
      const stageId = resolveLiveStageId(run, jobRunning, logEntries);
      return filterByStage(errors, stageId).slice(-3);
    }
    return errors;
  }, [logEntries, activityLogTab, selectedStageId, run, jobRunning]);

  const pinnedWarnings = useMemo(() => {
    if (activityLogTab === "all") return [];
    const warnings = filterWarnings(logEntries).slice(-3);
    if (activityLogTab === "step") {
      return filterByStage(warnings, selectedStageId).slice(-2);
    }
    if (activityLogTab === "live") {
      const stageId = resolveLiveStageId(run, jobRunning, logEntries);
      return filterByStage(warnings, stageId).slice(-2);
    }
    return warnings;
  }, [logEntries, activityLogTab, selectedStageId, run, jobRunning]);

  const scrollEntries = useMemo(() => {
    const pinned = [...pinnedErrors, ...pinnedWarnings];
    const withoutPinned = excludePinnedEntries(displayed, pinned);
    const deduped =
      activityLogTab === "all"
        ? dedupeConsecutiveLogEntries(withoutPinned)
        : withoutPinned;
    return deduped.slice(-200);
  }, [displayed, pinnedErrors, pinnedWarnings, activityLogTab]);

  const selectActivityTab = (tab: LogStreamTab) => {
    userPinnedActivityTabRef.current = true;
    setActivityLogTab(tab);
  };

  useEffect(() => {
    const wasRunning = prevJobRunningRef.current;
    prevJobRunningRef.current = jobRunning;
    if (jobRunning && !wasRunning) {
      userPinnedActivityTabRef.current = false;
    }
  }, [jobRunning]);

  useEffect(() => {
    if (userPinnedActivityTabRef.current) {
      if (jobRunning && activityLogTab !== "step" && activityLogTab !== "live") {
        setActivityLogTab("live");
      }
      return;
    }
    if (jobRunning && activityLogTab !== "step") {
      setActivityLogTab("live");
      return;
    }
    const focusStage = resolveFocusStageId(run, selectedStageId);
    if (!jobRunning && focusStage && activityLogTab === "live") {
      setActivityLogTab("step");
    }
  }, [jobRunning, activityLogTab, setActivityLogTab, run, selectedStageId]);

  useEffect(() => {
    if (userPinnedActivityTabRef.current) return;
    if (toolView && !jobRunning && activityLogTab === "step") {
      setActivityLogTab("all");
    }
  }, [toolView, jobRunning, activityLogTab, setActivityLogTab]);

  useEffect(() => {
    if (activityLogTab === "live" && displayed.length) {
      setLiveSeenTs(displayed[displayed.length - 1].ts);
    }
  }, [activityLogTab, displayed]);

  useEffect(() => {
    if (!autoScroll || userScrolledRef.current || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [scrollEntries, autoScroll]);

  const emptyMessage =
    activityLogTab === "step"
      ? selectedStageId
        ? "No activity for this step yet — run it or switch to Live."
        : "Select a pipeline step."
      : activityLogTab === "live"
        ? "Waiting for activity…"
        : "Log entries appear here as the pipeline runs.";

  if (activityLogCollapsed) {
    return (
      <aside className="activity-log-panel activity-log-collapsed panel">
        <button
          type="button"
          className="btn ghost sm activity-log-expand"
          onClick={() => setActivityLogCollapsed(false)}
        >
          Show activity log
        </button>
      </aside>
    );
  }

  return (
    <aside
      className={`activity-log-panel panel${variant === "global" ? " activity-log-panel--global" : ""}`}
      aria-label="Pipeline activity log"
    >
      <div className="activity-log-head panel-head">
        <div>
          <h3>Activity</h3>
          {activityLogTab === "step" && activeSubstep ? (
            <p className="hint sm activity-log-substep-context">
              {activeSubstep.status === "running" ? (
                <span className="spinner-inline" aria-hidden />
              ) : activeSubstep.status === "error" ? (
                <span className="log-level-dot level-error" aria-hidden />
              ) : null}
              {activeSubstep.label}
            </p>
          ) : null}
        </div>
        <div className="activity-log-head-actions">
          {onDumpLast ? (
            <button
              type="button"
              className="btn ghost sm"
              data-testid="action-trace-dump-last"
              data-action-id="gui.activity.dump_last"
              onClick={() => onDumpLast()}
            >
              Dump last step
            </button>
          ) : null}
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => setActivityLogCollapsed(true)}
            title="Collapse"
          >
            Hide
          </button>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => setActiveTab("logs")}
          >
            Full log
          </button>
        </div>
      </div>

      <div className="activity-log-tabs" role="tablist">
        {(
          [
            ["live", "Live", liveNewCount],
            ["step", "This step", 0],
            ["all", "All", 0],
          ] as const
        ).map(([tab, label, badge]) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activityLogTab === tab}
            className={`activity-log-tab${activityLogTab === tab ? " active" : ""}${
              tab === "live" && activeStream.isLive ? " live-stream" : ""
            }`}
            data-testid={`activity-log-${tab}`}
            onClick={() => selectActivityTab(tab)}
          >
            {label}
            {tab === "live" && activeStream.isLive ? (
              <span className="activity-live-chip">LIVE</span>
            ) : null}
            {badge > 0 ? (
              <span className="activity-log-tab-badge">{badge}</span>
            ) : null}
          </button>
        ))}
      </div>

      {toolView ? (
        <p className="hint sm activity-log-stream-label">
          Viewing all activity while using {pipelineSubTab.replace(/_/g, " ")} tools.
        </p>
      ) : null}
      {activityLogTab === "live" && activeStream.label ? (
        <p className="hint sm activity-log-stream-label">{activeStream.label}</p>
      ) : null}
      {activityLogTab === "step" && selectedStageId ? (
        <p className="hint sm activity-log-stream-label">
          Filtered to current step
        </p>
      ) : null}

      {(activityLogTab === "live" || activityLogTab === "step") &&
      (pinnedErrors.length || pinnedWarnings.length) ? (
        <div className="activity-log-pinned">
          {pinnedErrors.map((e, i) => (
            <div key={`err-${e.ts}-${i}`} className="log-entry level-error log-entry-compact">
              <span className="log-msg">{e.message}</span>
            </div>
          ))}
          {pinnedWarnings.map((e, i) => (
            <div key={`warn-${e.ts}-${i}`} className="log-entry level-warning log-entry-compact">
              <span className="log-msg">{e.message}</span>
            </div>
          ))}
        </div>
      ) : null}

      <div
        ref={scrollRef}
        className="activity-log-body prompt-log"
        role="log"
        aria-live="polite"
        onScroll={() => {
          if (!scrollRef.current) return;
          const el = scrollRef.current;
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
          userScrolledRef.current = !atBottom;
        }}
      >
        <LogEntryList
          entries={scrollEntries}
          run={run}
          emptyMessage={emptyMessage}
          compact={activityLogTab === "live"}
          onStageClick={(stageId) => {
            setLogFilterPreset({ stage: stageId, stream: "all" });
            setActiveTab("logs");
          }}
        />
      </div>

      <label className="activity-log-autoscroll logs-filter-check">
        <input
          type="checkbox"
          checked={autoScroll}
          onChange={(e) => {
            setAutoScroll(e.target.checked);
            userScrolledRef.current = !e.target.checked;
          }}
        />
        Auto-scroll
      </label>
    </aside>
  );
}
