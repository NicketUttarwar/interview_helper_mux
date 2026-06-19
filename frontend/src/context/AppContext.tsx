import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError } from "../api/client";
import type {
  AppConfig,
  AppTab,
  AssetFile,
  ExecuteBody,
  JobState,
  LogEntry,
  LogFilterPreset,
  LogStreamTab,
  OpenRunOptions,
  PipelineSubTab,
  RunData,
  RunSummary,
  SessionActive,
  StageInfo,
  TimelineData,
  TranscriptReviewState,
} from "../types";
import { isJobActivelyRunning } from "../utils/jobStatus";
import { countRequiredAttention } from "../utils/attentionQueue";
import { resolvePendingAction } from "../utils/pendingAction";
import { pendingActionToSubstep } from "../utils/stageSubsteps";
import {
  actionSummaryText,
  findHandoffStage,
  findPendingFocusStage,
  getHandoffPathsLocal,
} from "../utils/checkpoint";
import { ALL_API_CONSENTS, mapGateToStage } from "../utils";
import {
  findActiveStage,
  findNextRunnableStage,
  hasActionRequiredStage,
} from "../utils/preclean";
import { pendingWriteInfo, resolvePendingWritePaths, stageAwaitingWriteApproval } from "../utils/writeApproval";
import { describeExecuteBody } from "../utils/operatorActionLog";
import { activateSubstep as activateSubstepUtil } from "../utils/activateSubstep";
import type { StageSubstep } from "../types";

interface AppContextValue {
  activeTab: AppTab;
  pipelineSubTab: PipelineSubTab;
  config: AppConfig | null;
  runId: string | null;
  run: RunData | null;
  selectedStageId: string | null;
  selectedAsset: string | null;
  timeline: TimelineData | null;
  logEntries: LogEntry[];
  homeLog: LogEntry[];
  assets: AssetFile[];
  runs: RunSummary[];
  apiGrants: Record<string, boolean>;
  alertsMuted: boolean;
  toast: string | null;
  jobRunning: boolean;
  actionBusy: boolean;
  transcriptReview: TranscriptReviewState | null;
  selectedStage: StageInfo | undefined;
  actionModalOpen: boolean;
  pendingActionCount: number;
  actionSummary: string | null;
  confirmMessage: string | null;
  menuOpen: boolean;
  serverActiveRunId: string | null;
  sessionReady: boolean;
  sessionLoadError: string | null;
  openRunLoading: boolean;
  homeRefreshing: boolean;
  activityLogTab: LogStreamTab;
  activityLogCollapsed: boolean;
  logFilterPreset: LogFilterPreset | null;
  jobCompleteAt: number | null;
  activeSubstepId: string | null;
  pipelineCollapsedStages: string[];
  pipelineExpandedDoneStages: string[];
  pipelineFilterNeedsYou: boolean;
  setActivityLogTab: (tab: LogStreamTab) => void;
  setActivityLogCollapsed: (collapsed: boolean) => void;
  setLogFilterPreset: (preset: LogFilterPreset | null) => void;
  pinSelectedStage: () => void;
  setActiveTab: (tab: AppTab) => void;
  setPipelineSubTab: (tab: PipelineSubTab) => void;
  openArtifactInEditor: (path: string) => void;
  setSelectedAsset: (path: string | null) => void;
  setMenuOpen: (open: boolean) => void;
  showToast: (msg: string) => void;
  openActionModal: () => void;
  closeActionModal: () => void;
  clearSession: () => Promise<void>;
  refreshHome: (opts?: { enrichRuns?: boolean }) => Promise<void>;
  startRun: (inputPath: string, flowIntent?: string) => Promise<void>;
  openRun: (runId: string, opts?: OpenRunOptions) => Promise<void>;
  retryOpenRun: () => Promise<void>;
  refreshRun: () => Promise<RunData | null>;
  selectStage: (stageId: string) => Promise<void>;
  executeJob: (body: ExecuteBody) => Promise<void>;
  runNextStage: () => Promise<void>;
  redoFromStage: () => Promise<void>;
  startJobPoll: () => void;
  acknowledgeHandoff: () => Promise<void>;
  approveWriteAndContinue: (stageId?: string) => Promise<boolean>;
  onCheckpointContinue: () => Promise<void>;
  setAlertsMuted: (muted: boolean) => void;
  appendClientLog: (message: string, level?: string, stage?: string) => void;
  loadTranscriptReview: () => Promise<TranscriptReviewState | null>;
  setTranscriptReview: (data: TranscriptReviewState | null) => void;
  confirm: (message: string) => Promise<boolean>;
  resolveConfirm: (ok: boolean) => void;
  activateSubstep: (substep: StageSubstep, opts?: { openModal?: boolean }) => void;
  setActiveSubstepId: (id: string | null) => void;
  expandStage: (stageId: string) => void;
  collapseStage: (stageId: string) => void;
  toggleDoneStageExpanded: (stageId: string) => void;
  setPipelineFilterNeedsYou: (enabled: boolean) => void;
}

const AppContext = createContext<AppContextValue | null>(null);
const GUI_SERVER_STARTED_AT_KEY = "gui_server_started_at";

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}

function playAttentionPing(muted: boolean): void {
  if (muted) return;
  try {
    const ctx = new (window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.value = 0.12;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
    osc.stop(ctx.currentTime + 0.25);
  } catch {
    /* Web Audio unavailable */
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeTab, setActiveTabState] = useState<AppTab>("start");
  const [pipelineSubTab, setPipelineSubTab] = useState<PipelineSubTab>("stage");
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunData | null>(null);
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [homeLog, setHomeLog] = useState<LogEntry[]>([]);
  const [assets, setAssets] = useState<AssetFile[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [alertsMuted, setAlertsMutedState] = useState(
    () => localStorage.getItem("gui_mute_alerts") === "1",
  );
  const [toast, setToast] = useState<string | null>(null);
  const [jobRunning, setJobRunning] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const jobRunningRef = useRef(false);
  const actionBusyRef = useRef(false);
  const [transcriptReview, setTranscriptReview] =
    useState<TranscriptReviewState | null>(null);
  const [actionModalOpen, setActionModalOpen] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [serverActiveRunId, setServerActiveRunId] = useState<string | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [sessionLoadError, setSessionLoadError] = useState<string | null>(null);
  const [openRunLoading, setOpenRunLoading] = useState(false);
  const [homeRefreshing, setHomeRefreshing] = useState(false);
  const [shownPrecleanOffers, setShownPrecleanOffers] = useState<Set<string>>(
    () => new Set(),
  );
  const [activityLogTab, setActivityLogTabState] = useState<LogStreamTab>("live");
  const [activityLogCollapsed, setActivityLogCollapsedState] = useState(false);
  const [logFilterPreset, setLogFilterPresetState] = useState<LogFilterPreset | null>(
    null,
  );
  const [jobCompleteAt, setJobCompleteAt] = useState<number | null>(null);
  const [activeSubstepId, setActiveSubstepIdState] = useState<string | null>(null);
  const [pipelineCollapsedStages, setPipelineCollapsedStages] = useState<string[]>([]);
  const [pipelineExpandedDoneStages, setPipelineExpandedDoneStages] = useState<string[]>(
    [],
  );
  const [pipelineFilterNeedsYou, setPipelineFilterNeedsYouState] = useState(false);

  const logCountRef = useRef(0);
  const bootGenRef = useRef(0);
  const persistUiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runIdRef = useRef<string | null>(null);
  const selectedStageIdRef = useRef<string | null>(null);
  const activeTabRef = useRef<AppTab>("start");
  const pipelineSubTabRef = useRef<PipelineSubTab>("stage");
  const activityLogTabRef = useRef<LogStreamTab>("live");
  const activityLogCollapsedRef = useRef(false);
  const pipelineCollapsedRef = useRef<string[]>([]);
  const pipelineExpandedDoneRef = useRef<string[]>([]);
  const pipelineFilterNeedsYouRef = useRef(false);
  const lastNotifiedTsRef = useRef<string | null>(null);
  const lastActionRequiredIdRef = useRef<string | null>(null);
  const jobStatusPrevRef = useRef<string | null>(null);
  const confirmResolveRef = useRef<((ok: boolean) => void) | null>(null);
  const jobPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const userDismissedActionRef = useRef(false);
  const userPinnedStageAtRef = useRef<number | null>(null);
  const runRefreshTickRef = useRef(0);

  const selectedStage = useMemo(
    () => run?.stages.find((s) => s.id === selectedStageId),
    [run, selectedStageId],
  );

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    const extended = jobRunningRef.current || actionBusyRef.current;
    toastTimerRef.current = window.setTimeout(
      () => setToast(null),
      extended ? 7000 : 3500,
    ) as unknown as ReturnType<typeof setTimeout>;
  }, []);

  const mergedApiGrants = useCallback(() => ALL_API_CONSENTS, []);

  const pendingActionCount = useMemo(
    () => countRequiredAttention(run, mergedApiGrants()),
    [run, mergedApiGrants],
  );
  const actionSummary = useMemo(
    () => actionSummaryText(run, mergedApiGrants()),
    [run, mergedApiGrants],
  );

  useEffect(() => {
    jobRunningRef.current = jobRunning;
  }, [jobRunning]);
  useEffect(() => {
    actionBusyRef.current = actionBusy;
  }, [actionBusy]);

  useEffect(() => {
    runIdRef.current = runId;
  }, [runId]);
  useEffect(() => {
    selectedStageIdRef.current = selectedStageId;
  }, [selectedStageId]);
  useEffect(() => {
    activeTabRef.current = activeTab;
  }, [activeTab]);
  useEffect(() => {
    pipelineSubTabRef.current = pipelineSubTab;
  }, [pipelineSubTab]);
  useEffect(() => {
    activityLogTabRef.current = activityLogTab;
  }, [activityLogTab]);
  useEffect(() => {
    activityLogCollapsedRef.current = activityLogCollapsed;
  }, [activityLogCollapsed]);

  useEffect(() => {
    activityLogCollapsedRef.current = activityLogCollapsed;
  }, [activityLogCollapsed]);
  useEffect(() => {
    pipelineCollapsedRef.current = pipelineCollapsedStages;
  }, [pipelineCollapsedStages]);
  useEffect(() => {
    pipelineExpandedDoneRef.current = pipelineExpandedDoneStages;
  }, [pipelineExpandedDoneStages]);
  useEffect(() => {
    pipelineFilterNeedsYouRef.current = pipelineFilterNeedsYou;
  }, [pipelineFilterNeedsYou]);

  const setActiveSubstepId = useCallback((id: string | null) => {
    setActiveSubstepIdState(id);
  }, []);

  const expandStage = useCallback((stageId: string) => {
    setPipelineCollapsedStages((prev) => prev.filter((id) => id !== stageId));
  }, []);

  const collapseStage = useCallback((stageId: string) => {
    setPipelineCollapsedStages((prev) => (prev.includes(stageId) ? prev : [...prev, stageId]));
  }, []);

  const toggleDoneStageExpanded = useCallback((stageId: string) => {
    setPipelineExpandedDoneStages((prev) =>
      prev.includes(stageId) ? prev.filter((id) => id !== stageId) : [...prev, stageId],
    );
  }, []);

  const pinSelectedStage = useCallback(() => {
    userPinnedStageAtRef.current = Date.now();
  }, []);

  const persistSessionUi = useCallback(() => {
    const rid = runIdRef.current;
    if (!rid) return;
    if (persistUiTimerRef.current) clearTimeout(persistUiTimerRef.current);
    persistUiTimerRef.current = setTimeout(() => {
      void api("/api/session/active", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: rid,
          selected_stage_id: selectedStageIdRef.current,
          active_tab: activeTabRef.current,
          pipeline_sub_tab: pipelineSubTabRef.current,
          activity_log_tab: activityLogTabRef.current,
          activity_log_collapsed: activityLogCollapsedRef.current,
          pipeline_collapsed_stages: pipelineCollapsedRef.current,
          pipeline_expanded_done_stages: pipelineExpandedDoneRef.current,
          pipeline_filter_needs_you: pipelineFilterNeedsYouRef.current,
        }),
      }).catch(() => {});
    }, 200);
  }, []);

  const setPipelineFilterNeedsYou = useCallback(
    (enabled: boolean) => {
      setPipelineFilterNeedsYouState(enabled);
      pipelineFilterNeedsYouRef.current = enabled;
      persistSessionUi();
    },
    [persistSessionUi],
  );

  const setActivityLogTab = useCallback(
    (tab: LogStreamTab) => {
      setActivityLogTabState(tab);
      activityLogTabRef.current = tab;
      persistSessionUi();
    },
    [persistSessionUi],
  );

  const setActivityLogCollapsed = useCallback(
    (collapsed: boolean) => {
      setActivityLogCollapsedState(collapsed);
      activityLogCollapsedRef.current = collapsed;
      persistSessionUi();
    },
    [persistSessionUi],
  );

  const setLogFilterPreset = useCallback((preset: LogFilterPreset | null) => {
    setLogFilterPresetState(preset);
  }, []);

  const setActiveTab = useCallback(
    (tab: AppTab) => {
      setActiveTabState(tab);
      activeTabRef.current = tab;
      persistSessionUi();
    },
    [persistSessionUi],
  );

  const setPipelineSubTabWrapped = useCallback(
    (tab: PipelineSubTab) => {
      setPipelineSubTab(tab);
      pipelineSubTabRef.current = tab;
      persistSessionUi();
    },
    [persistSessionUi],
  );

  const openArtifactInEditor = useCallback(
    (path: string) => {
      setPipelineSubTabWrapped("files");
      window.dispatchEvent(new CustomEvent("handoff-open", { detail: { path } }));
    },
    [setPipelineSubTabWrapped],
  );

  const closeActionModal = useCallback(() => {
    userDismissedActionRef.current = true;
    setActionModalOpen(false);
  }, []);

  const confirm = useCallback((message: string) => {
    return new Promise<boolean>((resolve) => {
      setConfirmMessage(message);
      confirmResolveRef.current = resolve;
    });
  }, []);

  const resolveConfirm = useCallback((ok: boolean) => {
    setConfirmMessage(null);
    confirmResolveRef.current?.(ok);
    confirmResolveRef.current = null;
  }, []);

  const setAlertsMuted = useCallback((muted: boolean) => {
    localStorage.setItem("gui_mute_alerts", muted ? "1" : "0");
    setAlertsMutedState(muted);
  }, []);

  const renderLogWithAlerts = useCallback(
    (entries: LogEntry[]) => {
      setLogEntries(entries);
      const prevCount = logCountRef.current;
      logCountRef.current = entries.length;
      if (entries.length > prevCount) {
        const newest = entries[entries.length - 1];
        if (newest.level === "action" && newest.ts !== lastNotifiedTsRef.current) {
          lastNotifiedTsRef.current = newest.ts;
          playAttentionPing(alertsMuted);
        }
      }
    },
    [alertsMuted],
  );

  const refreshHome = useCallback(async (opts: { enrichRuns?: boolean } = {}) => {
    const enrichRuns = opts.enrichRuns !== false;
    setHomeRefreshing(true);
    const errors: string[] = [];
    const track = <T,>(
      promise: Promise<T>,
      onOk: (value: T) => void,
      errorLabel: string,
    ) =>
      promise
        .then(onOk)
        .catch((reason) => {
          errors.push(
            reason instanceof ApiError
              ? `${errorLabel}: ${reason.message}`
              : `${errorLabel}: request failed`,
          );
        });

    const runsPath = enrichRuns
      ? "/api/runs?enrich=1&enrich_limit=50"
      : "/api/runs";

    await Promise.allSettled([
      track(
        api<{ files?: AssetFile[] }>("/api/assets"),
        (data) => setAssets(data.files ?? []),
        "Source audio",
      ),
      track(
        api<{ runs?: RunSummary[] }>(runsPath),
        (data) => setRuns(data.runs ?? []),
        "Executions",
      ),
      track(
        api<{ log?: LogEntry[]; active?: { run_id?: string } | null }>(
          "/api/session",
        ),
        (session) => {
          setHomeLog(session.log?.slice(-5) || []);
          setServerActiveRunId(session.active?.run_id ?? null);
        },
        "Session",
      ),
    ]);

    setHomeRefreshing(false);
    if (errors.length) showToast(errors.join(" · "));
  }, [showToast]);

  const pollLog = useCallback(async (force?: boolean) => {
    if (!runId) return;
    try {
      const data = await api<{ entries: LogEntry[] }>(
        `/api/runs/${runId}/log?tail=500`,
      );
      if (force || data.entries?.length !== logCountRef.current) {
        renderLogWithAlerts(data.entries);
        setRun((prev) =>
          prev ? { ...prev, log_tail: data.entries } : prev,
        );
      }
    } catch {
      /* ignore */
    }
  }, [runId, renderLogWithAlerts]);

  const appendClientLogInternal = async (
    rid: string | null,
    message: string,
    level = "info",
    stage?: string,
  ) => {
    if (!rid) {
      renderLogWithAlerts([
        { ts: new Date().toISOString(), level: level as LogEntry["level"], message, stage },
      ]);
      return;
    }
    await api(`/api/runs/${rid}/log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, level, stage }),
    });
    await pollLog();
  };

  const appendClientLog = useCallback(
    (message: string, level = "info", stage?: string) => {
      void appendClientLogInternal(runId, message, level, stage);
    },
    [runId, pollLog],
  );

  const logOperatorAction = useCallback(
    (message: string, stage?: string | null) => {
      appendClientLog(message, "action", stage || selectedStageIdRef.current || undefined);
    },
    [appendClientLog],
  );

  const stopJobPoll = useCallback(() => {
    if (jobPollRef.current) {
      clearInterval(jobPollRef.current);
      jobPollRef.current = null;
    }
    setJobRunning(false);
  }, []);

  const refreshRun = useCallback(async (): Promise<RunData | null> => {
    if (!runId) return null;
    const runData = await api<RunData>(`/api/runs/${runId}`);
    setRun(runData);
    setShownPrecleanOffers(
      new Set(runData.meta?.audio_preclean?.offered_at || []),
    );
    const tl = await api<TimelineData>(`/api/runs/${runId}/timeline`).catch(
      () => null,
    );
    setTimeline(tl);
    renderLogWithAlerts(runData.log_tail || []);
    return runData;
  }, [runId, renderLogWithAlerts]);

  const selectStage = useCallback(
    async (stageId: string, opts?: { pinned?: boolean }) => {
      if (opts?.pinned !== false) {
        userPinnedStageAtRef.current = Date.now();
      }
      setSelectedStageId(stageId);
      selectedStageIdRef.current = stageId;
      persistSessionUi();
    },
    [persistSessionUi],
  );

  const maybeAutoSelectRunningStage = useCallback(
    (job: JobState | null | undefined) => {
      if (!job || !isJobActivelyRunning(job)) return;
      const stageId = job.current_stage || job.stage;
      if (!stageId) return;
      const pinnedAt = userPinnedStageAtRef.current;
      if (pinnedAt && Date.now() - pinnedAt < 30_000) return;
      if (selectedStageIdRef.current === stageId) return;
      setSelectedStageId(stageId);
      selectedStageIdRef.current = stageId;
    },
    [],
  );

  const focusPendingStage = useCallback(async () => {
    if (!run) return;
    const stageId = findPendingFocusStage(run, mergedApiGrants());
    if (stageId) await selectStage(stageId);
  }, [run, mergedApiGrants, selectStage]);

  const openActionModal = useCallback(() => {
    userDismissedActionRef.current = false;
    setActionModalOpen(true);
    void focusPendingStage();
  }, [focusPendingStage]);

  const syncJobRunning = useCallback(async (rid: string) => {
    try {
      const job = await api<JobState>(`/api/runs/${rid}/job`);
      const active = isJobActivelyRunning(job);
      setJobRunning(active);
      setRun((prev) => (prev ? { ...prev, job } : prev));
      maybeAutoSelectRunningStage(job);
      return job;
    } catch {
      setJobRunning(false);
      return null;
    }
  }, [maybeAutoSelectRunningStage]);

  const startJobPoll = useCallback(() => {
    stopJobPoll();
    if (!runId) return;
    void (async () => {
      const job = await syncJobRunning(runId);
      if (!isJobActivelyRunning(job)) return;
      setJobRunning(true);
      runRefreshTickRef.current = 0;
      jobPollRef.current = setInterval(async () => {
        try {
          const polled = await api<JobState>(`/api/runs/${runId}/job`);
          setRun((prev) => (prev ? { ...prev, job: polled } : prev));
          maybeAutoSelectRunningStage(polled);
          if (!isJobActivelyRunning(polled)) {
            const refreshed = await refreshRun();
            stopJobPoll();
            void focusPendingStage();
            if (polled.status === "complete") {
              setJobCompleteAt(Date.now());
              const next = refreshed?.journey?.next_action;
              if (next) {
                showToast(`Next: ${next}`);
                if (runId) {
                  void api(`/api/runs/${runId}/log`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      message: `Step finished — next: ${next}`,
                      level: "info",
                    }),
                  }).then(() => pollLog());
                }
              }
            }
            if (
              polled.status === "awaiting_write_approval" ||
              polled.awaiting_write_approval
            ) {
              if (!userDismissedActionRef.current) {
                openActionModal();
                playAttentionPing(alertsMuted);
              }
            }
          } else {
            runRefreshTickRef.current += 1;
            if (runRefreshTickRef.current % 5 === 0) {
              await refreshRun();
            }
          }
          await pollLog(true);
        } catch {
          stopJobPoll();
        }
      }, 1000);
    })();
  }, [
    runId,
    refreshRun,
    stopJobPoll,
    pollLog,
    openActionModal,
    alertsMuted,
    syncJobRunning,
    maybeAutoSelectRunningStage,
    focusPendingStage,
    showToast,
    pollLog,
  ]);

  const executeJob = useCallback(
    async (body: ExecuteBody) => {
      if (!runId) return;
      const handoffStage = findHandoffStage(run);
      if (handoffStage) {
        showToast(
          `Review outputs from ${handoffStage.title} on the Pipeline tab, then acknowledge to continue.`,
        );
        await selectStage(handoffStage.id);
        return;
      }
      const payload = { ...body, api_consents: ALL_API_CONSENTS };
      const stageForLog = body.stage || body.from_stage || undefined;
      logOperatorAction(describeExecuteBody(body), stageForLog);
      try {
        const res = await api<{
          ok?: boolean;
          error?: string;
          needs_stage_reuse?: boolean;
          stage?: string;
        }>(`/api/runs/${runId}/execute`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (res.ok === false) {
          appendClientLog(res.error || "Failed to start job", "warning", stageForLog);
          showToast(res.error || "Failed to start");
          const busyJob = (res as { job?: JobState }).job;
          if (busyJob && isJobActivelyRunning(busyJob)) {
            setRun((prev) => (prev ? { ...prev, job: busyJob } : prev));
            setJobRunning(true);
            setActivityLogTabState("live");
            activityLogTabRef.current = "live";
            setActivityLogCollapsedState(false);
            activityLogCollapsedRef.current = false;
            startJobPoll();
          }
          if (res.needs_stage_reuse && res.stage) {
            await selectStage(res.stage);
            openActionModal();
            playAttentionPing(alertsMuted);
            await refreshRun();
            return;
          }
          const writePending = res as {
            awaiting_write_approval?: boolean;
            pending_write_stage?: string;
          };
          if (writePending.awaiting_write_approval && writePending.pending_write_stage) {
            await selectStage(writePending.pending_write_stage);
            openActionModal();
            playAttentionPing(alertsMuted);
            await refreshRun();
            return;
          }
          return;
        }
        appendClientLog("Pipeline job started — streaming logs below.", "info", stageForLog);
        setActivityLogTabState("live");
        activityLogTabRef.current = "live";
        setActivityLogCollapsedState(false);
        activityLogCollapsedRef.current = false;
        startJobPoll();
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          const msg =
            e.message ||
            "Run is busy — watch Activity for progress, or refresh after a server restart.";
          appendClientLog(msg, "warning", stageForLog);
          showToast(msg);
          const job = runId ? await syncJobRunning(runId) : null;
          if (isJobActivelyRunning(job)) {
            setActivityLogTabState("live");
            activityLogTabRef.current = "live";
            startJobPoll();
          } else await refreshRun();
          return;
        }
        const msg = e instanceof Error ? e.message : "Failed to start job";
        appendClientLog(msg, "warning", stageForLog);
        showToast(msg);
      }
    },
    [
      runId,
      run,
      alertsMuted,
      showToast,
      refreshRun,
      startJobPoll,
      selectStage,
      openActionModal,
      syncJobRunning,
      logOperatorAction,
      appendClientLog,
    ],
  );

  const openRun = useCallback(
    async (id: string, opts: OpenRunOptions = {}) => {
      if (!sessionReady && opts.quiet) {
        /* boot path sets sessionReady after */
      } else if (!sessionReady) {
        showToast("Session is still loading — try again in a moment.");
        return;
      }
      if (runId && id !== runId && !opts.force) {
        showToast("This session is locked to one source. Clear session to open another run.");
        return;
      }
      const stageId = opts.selectedStageId ?? selectedStageIdRef.current;
      const tab = opts.activeTab ?? "pipeline";
      const subTab = opts.pipelineSubTab ?? "stage";
      setOpenRunLoading(true);
      setSessionLoadError(null);
      setRunId(id);
      setActiveTabState(tab);
      activeTabRef.current = tab;
      setPipelineSubTab(subTab);
      pipelineSubTabRef.current = subTab;
      userDismissedActionRef.current = false;
      try {
        await api("/api/session/active", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            run_id: id,
            selected_stage_id: stageId,
            active_tab: tab,
            pipeline_sub_tab: subTab,
          }),
        });
        const runData = await api<RunData>(`/api/runs/${id}`);
        setRun(runData);
        setShownPrecleanOffers(
          new Set(runData.meta?.audio_preclean?.offered_at || []),
        );
        const tl = await api<TimelineData>(`/api/runs/${id}/timeline`).catch(
          () => null,
        );
        setTimeline(tl);
        renderLogWithAlerts(runData.log_tail || []);
        const resolvedStage =
          stageId ||
          findActiveStage(runData.stages)?.id ||
          runData.stages[0]?.id ||
          null;
        if (resolvedStage) {
          setSelectedStageId(resolvedStage);
          selectedStageIdRef.current = resolvedStage;
          persistSessionUi();
        }
        if (!opts.quiet) {
          await appendClientLogInternal(id, `Opened execution ${id}`, "info");
        }
        const job = await syncJobRunning(id);
        if (isJobActivelyRunning(job)) startJobPoll();
        else setJobRunning(false);
        setServerActiveRunId(id);
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Failed to open execution";
        setSessionLoadError(msg);
        setRun(null);
        showToast(msg);
        throw e;
      } finally {
        setOpenRunLoading(false);
      }
    },
    [
      renderLogWithAlerts,
      startJobPoll,
      runId,
      showToast,
      sessionReady,
      persistSessionUi,
      syncJobRunning,
    ],
  );

  const retryOpenRun = useCallback(async () => {
    const id = runId || serverActiveRunId;
    if (!id) return;
    await openRun(id, { quiet: true, force: true });
  }, [runId, serverActiveRunId, openRun]);

  const startRun = useCallback(
    async (inputPath: string, flowIntent?: string) => {
      if (!sessionReady) {
        showToast("Session is still loading — try again in a moment.");
        return;
      }
      if (runId) {
        showToast("Source audio is locked for this session. Clear session to start over.");
        setActiveTabState("pipeline");
        return;
      }
      try {
        const body: Record<string, string> = { input_audio_path: inputPath };
        if (flowIntent) body.flow_intent = flowIntent;
        const res = await api<{ run_id: string }>("/api/runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        appendClientLog(`Created execution ${res.run_id}`, "success");
        await openRun(res.run_id);
      } catch (e) {
        showToast(e instanceof Error ? e.message : "Failed to start run");
      }
    },
    [appendClientLog, openRun, showToast, runId, sessionReady],
  );

  const clearSession = useCallback(async () => {
    if (!sessionReady) return;
    stopJobPoll();
    try {
      await api("/api/session/active", { method: "DELETE" });
    } catch {
      await api("/api/session/active", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: null }),
      }).catch(() => {});
    }
    setRunId(null);
    runIdRef.current = null;
    setRun(null);
    setTimeline(null);
    setSelectedStageId(null);
    selectedStageIdRef.current = null;
    setServerActiveRunId(null);
    setSessionLoadError(null);
    setActionModalOpen(false);
    setActiveTabState("start");
    activeTabRef.current = "start";
    await refreshHome();
  }, [stopJobPoll, refreshHome, sessionReady]);

  const acknowledgeHandoff = useCallback(async () => {
    if (!runId) return;
    const stageId =
      (run ? findHandoffStage(run)?.id : null) || selectedStageId || null;
    if (!stageId) return;
    logOperatorAction(`Acknowledging AI review for ${stageId.replace(/_/g, " ")}…`, stageId);
    try {
      await api(`/api/runs/${runId}/handoff-ack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage_id: stageId }),
      });
      showToast("Handoff acknowledged.");
      setActionModalOpen(false);
      userDismissedActionRef.current = false;
      await refreshRun();
      await pollLog(true);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Handoff acknowledgment failed";
      appendClientLog(msg, "warning", stageId);
      showToast(msg);
    }
  }, [selectedStageId, runId, run, showToast, refreshRun, logOperatorAction, appendClientLog, pollLog]);

  const runNextStage = useCallback(async () => {
    const current = runId ? await refreshRun() : run;
    if (!current) return;
    const write = pendingWriteInfo(current);
    if (write?.paths.length) {
      const sid = write.stageId;
      if (sid) {
        await selectStage(sid);
        setPipelineSubTabWrapped("files");
      }
      showToast("Save staged outputs to disk before continuing.");
      if (!userDismissedActionRef.current) openActionModal();
      return;
    }
    if (
      current.job?.status === "awaiting_write_approval" ||
      current.job?.awaiting_write_approval
    ) {
      const sid = current.job.pending_write_stage || current.job.stage;
      if (sid) {
        await selectStage(sid);
        setPipelineSubTabWrapped("files");
      }
      showToast("Review stage outputs before saving to disk.");
      return;
    }
    if (current.job?.needs_stage_reuse && current.job.stage) {
      await selectStage(current.job.stage);
      setPipelineSubTabWrapped("stage");
      showToast("Choose reuse from a prior execution or run this step fresh.");
      return;
    }
    const handoffStage = findHandoffStage(current);
    if (handoffStage) {
      showToast(
        `Review outputs from ${handoffStage.title}, then acknowledge to continue.`,
      );
      await selectStage(handoffStage.id);
      setPipelineSubTabWrapped("stage");
      return;
    }
    if (hasActionRequiredStage(current.stages)) {
      const blocked = current.stages.find((s) => s.status === "action_required");
      showToast(
        `Complete checkpoint: ${blocked?.title || "action required"} before running.`,
      );
      if (blocked) {
        await selectStage(blocked.id);
        setPipelineSubTabWrapped("stage");
      }
      openActionModal();
      playAttentionPing(alertsMuted);
      return;
    }
    const next = findNextRunnableStage(current.stages);
    if (!next) {
      showToast("No runnable stage — check gates or flow.");
      return;
    }
    if (
      next.id === "transcript_review" ||
      next.id === "g1_vo_pickup" ||
      next.id === "g2_flow_select"
    ) {
      await selectStage(next.id);
      setPipelineSubTabWrapped("stage");
      openActionModal();
      return;
    }
    setActionModalOpen(false);
    userDismissedActionRef.current = false;
    await selectStage(next.id);
    setPipelineSubTab("stage");
    setActivityLogTabState("live");
    activityLogTabRef.current = "live";
    await executeJob({ mode: "stage", stage: next.id });
  }, [
    run,
    runId,
    alertsMuted,
    showToast,
    selectStage,
    executeJob,
    openActionModal,
    refreshRun,
    setPipelineSubTabWrapped,
  ]);

  const approveWriteAndContinue = useCallback(
    async (stageId?: string): Promise<boolean> => {
      if (!runId || !run) return false;
      const sid =
        stageId ||
        run.job?.pending_write_stage ||
        run.job?.stage ||
        pendingWriteInfo(run)?.stageId;
      if (!sid) {
        showToast("No staged outputs to save.");
        return false;
      }
      const paths = resolvePendingWritePaths(run, sid);
      if (!paths.length) {
        showToast("Staged files are not listed yet — try refresh.");
        return false;
      }
      setActionBusy(true);
      logOperatorAction(
        `Saving ${paths.length} staged file(s) for ${sid.replace(/_/g, " ")}…`,
        sid,
      );
      try {
        await api(`/api/runs/${runId}/pending-writes/${sid}/approve`, {
          method: "POST",
        });
        showToast("Outputs saved — continuing.");
        setActionModalOpen(false);
        userDismissedActionRef.current = false;
        const refreshed = await refreshRun();
        await pollLog(true);
        const stillPending = stageAwaitingWriteApproval(refreshed, sid);
        if (stillPending) {
          appendClientLog(
            "Save completed but review gate still active — refresh or retry.",
            "warning",
            sid,
          );
          return false;
        }
        await runNextStage();
        return true;
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Approve failed";
        appendClientLog(msg, "warning", sid);
        showToast(msg);
        if (e instanceof ApiError && e.status === 409 && runId) {
          const job = await syncJobRunning(runId);
          if (isJobActivelyRunning(job)) {
            setActivityLogTabState("live");
            activityLogTabRef.current = "live";
            startJobPoll();
          }
        }
        return false;
      } finally {
        setActionBusy(false);
      }
    },
    [
      runId,
      run,
      showToast,
      appendClientLog,
      refreshRun,
      runNextStage,
      logOperatorAction,
      pollLog,
      syncJobRunning,
      startJobPoll,
    ],
  );

  const onCheckpointContinue = useCallback(async () => {
    const current = runId ? await refreshRun() : run;
    if (!current || !selectedStage) return;
    const write = pendingWriteInfo(current);
    if (
      write &&
      (write.stageId === selectedStage.id ||
        selectedStage.status === "awaiting_write_approval")
    ) {
      await approveWriteAndContinue(write.stageId);
      return;
    }
    const paths = getHandoffPathsLocal(selectedStage, current.log_tail);
    if (selectedStage.status === "done" && paths.length) {
      setActionBusy(true);
      try {
        await acknowledgeHandoff();
        await runNextStage();
      } finally {
        setActionBusy(false);
      }
      return;
    }
    if (selectedStage.id === "g1_vo_pickup" && current.g1_clear) {
      await selectStage("g2_flow_select");
      setPipelineSubTabWrapped("stage");
      return;
    }
    setActionBusy(true);
    try {
      await runNextStage();
    } finally {
      setActionBusy(false);
    }
  }, [
    run,
    runId,
    selectedStage,
    approveWriteAndContinue,
    acknowledgeHandoff,
    refreshRun,
    runNextStage,
    selectStage,
    setPipelineSubTabWrapped,
  ]);

  const activateSubstep = useCallback(
    (substep: StageSubstep, opts?: { openModal?: boolean }) => {
      activateSubstepUtil(
        substep,
        {
          selectStage: (id) => void selectStage(id),
          setActiveTab,
          setPipelineSubTab: setPipelineSubTabWrapped,
          openActionModal,
          closeActionModal: () => setActionModalOpen(false),
          runNextStage: () => void runNextStage(),
          approveWrite: (id) => void approveWriteAndContinue(id),
          acknowledgeHandoff: () => void acknowledgeHandoff(),
          setActiveSubstepId,
        },
        opts,
      );
      expandStage(substep.stageId);
    },
    [
      selectStage,
      setActiveTab,
      setPipelineSubTabWrapped,
      openActionModal,
      runNextStage,
      approveWriteAndContinue,
      acknowledgeHandoff,
      setActiveSubstepId,
      expandStage,
    ],
  );

  const redoFromStage = useCallback(async () => {
    if (!selectedStageId || !runId) return;
    const ok = await confirm(`Redo from "${selectedStageId}"?`);
    if (!ok) return;
    try {
      await api(`/api/runs/${runId}/reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from_stage: mapGateToStage(selectedStageId) }),
      });
      appendClientLog(`Reset pipeline from ${selectedStageId}`, "action");
      await refreshRun();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Redo failed";
      showToast(msg);
      appendClientLog(msg, "warning");
    }
  }, [selectedStageId, runId, refreshRun, confirm, appendClientLog, showToast]);

  const loadTranscriptReview = useCallback(async () => {
    if (!runId) return null;
    const data = await api<TranscriptReviewState>(
      `/api/runs/${runId}/transcript-review`,
    );
    setTranscriptReview(data);
    return data;
  }, [runId]);

  useEffect(() => {
    const gen = ++bootGenRef.current;
    void (async () => {
      let active: SessionActive | null | undefined;
      let serverRestarted = false;
      try {
        const cfg = await api<AppConfig>("/api/config");
        if (gen !== bootGenRef.current) return;
        setConfig(cfg);
        const session = await api<{
          server?: { started_at?: string };
          active?: SessionActive | null;
          log?: LogEntry[];
        }>("/api/session");
        if (gen !== bootGenRef.current) return;
        const startedAt = session.server?.started_at;
        const prevStarted = localStorage.getItem(GUI_SERVER_STARTED_AT_KEY);
        serverRestarted = Boolean(startedAt && prevStarted && startedAt !== prevStarted);
        if (startedAt) localStorage.setItem(GUI_SERVER_STARTED_AT_KEY, startedAt);
        setServerActiveRunId(session.active?.run_id ?? null);
        // Fast boot path: assets + lightweight runs list — do not block on enrich=50.
        await refreshHome({ enrichRuns: false });
        if (gen !== bootGenRef.current) return;
        if (session.log?.length) renderLogWithAlerts(session.log);
        active = session.active;
      } catch (e) {
        if (gen !== bootGenRef.current) return;
        const msg = e instanceof Error ? e.message : "Failed to load session";
        setSessionLoadError(msg);
        showToast(msg);
      } finally {
        if (gen === bootGenRef.current) setSessionReady(true);
      }

      void (async () => {
        try {
          await refreshHome({ enrichRuns: true });
          if (gen !== bootGenRef.current) return;
          if (!active?.run_id) return;
          const stageId = active.selected_stage_id ?? null;
          selectedStageIdRef.current = stageId;
          setSelectedStageId(stageId);
          await openRun(active.run_id, {
            quiet: true,
            selectedStageId: stageId,
            activeTab: active.active_tab ?? "pipeline",
            pipelineSubTab: active.pipeline_sub_tab ?? "stage",
          });
          if (active.activity_log_tab) {
            setActivityLogTabState(active.activity_log_tab as LogStreamTab);
            activityLogTabRef.current = active.activity_log_tab as LogStreamTab;
          }
          if (typeof active.activity_log_collapsed === "boolean") {
            setActivityLogCollapsedState(active.activity_log_collapsed);
            activityLogCollapsedRef.current = active.activity_log_collapsed;
          }
          if (Array.isArray(active.pipeline_collapsed_stages)) {
            setPipelineCollapsedStages(active.pipeline_collapsed_stages);
            pipelineCollapsedRef.current = active.pipeline_collapsed_stages;
          }
          if (Array.isArray(active.pipeline_expanded_done_stages)) {
            setPipelineExpandedDoneStages(active.pipeline_expanded_done_stages);
            pipelineExpandedDoneRef.current = active.pipeline_expanded_done_stages;
          }
          if (typeof active.pipeline_filter_needs_you === "boolean") {
            setPipelineFilterNeedsYouState(active.pipeline_filter_needs_you);
            pipelineFilterNeedsYouRef.current = active.pipeline_filter_needs_you;
          }
          if (gen !== bootGenRef.current) return;
          if (serverRestarted && runIdRef.current) {
            const rid = runIdRef.current;
            await syncJobRunning(rid);
            const runData = await api<RunData>(`/api/runs/${rid}`);
            setRun(runData);
            renderLogWithAlerts(runData.log_tail || []);
          }
        } catch {
          /* enrich/restore failures surface via toasts from openRun/refreshHome */
        }
      })();
    })();
    logPollRef.current = setInterval(() => {
      void pollLog();
    }, 2000);
    return () => {
      if (logPollRef.current) clearInterval(logPollRef.current);
      stopJobPoll();
    };
  }, []);

  useEffect(() => {
    if (logPollRef.current) clearInterval(logPollRef.current);
    if (!runId) return;
    logPollRef.current = setInterval(() => {
      void pollLog();
    }, jobRunning ? 1000 : 2000);
    return () => {
      if (logPollRef.current) clearInterval(logPollRef.current);
    };
  }, [runId, jobRunning, pollLog]);

  useEffect(() => {
    if (!run) return;
    const job = run.job;
    const actionStage = run.stages.find((s) => s.status === "action_required");
    if (job?.status === "gate" || job?.status === "needs_operator") {
      if (jobStatusPrevRef.current !== job.status) playAttentionPing(alertsMuted);
    } else if (actionStage) {
      if (lastActionRequiredIdRef.current !== actionStage.id) {
        lastActionRequiredIdRef.current = actionStage.id;
        playAttentionPing(alertsMuted);
      }
    } else {
      lastActionRequiredIdRef.current = null;
    }
    jobStatusPrevRef.current = job?.status ?? null;
  }, [run, alertsMuted]);

  useEffect(() => {
    if (pendingActionCount === 0) {
      setActionModalOpen(false);
      userDismissedActionRef.current = false;
      return;
    }
    const pending = resolvePendingAction(run, mergedApiGrants());
    if (!pending) return;
    const sub = pendingActionToSubstep(pending);
    setActiveSubstepIdState(sub.id);
    setPipelineCollapsedStages((prev) => prev.filter((id) => id !== pending.stageId));
  }, [pendingActionCount, run, mergedApiGrants]);

  useEffect(() => {
    if (run?.journey?.active_substep_id) {
      setActiveSubstepIdState(run.journey.active_substep_id);
    }
  }, [run?.journey?.active_substep_id]);

  useEffect(() => {
    if (activeTab === "executions") void refreshHome();
  }, [activeTab, refreshHome]);

  const value: AppContextValue = {
    activeTab,
    pipelineSubTab,
    config,
    runId,
    run,
    selectedStageId,
    selectedAsset,
    timeline,
    logEntries,
    homeLog,
    assets,
    runs,
    apiGrants: ALL_API_CONSENTS,
    alertsMuted,
    toast,
    jobRunning,
    actionBusy,
    transcriptReview,
    selectedStage,
    actionModalOpen,
    pendingActionCount,
    actionSummary,
    confirmMessage,
    menuOpen,
    serverActiveRunId,
    sessionReady,
    sessionLoadError,
    openRunLoading,
    homeRefreshing,
    activityLogTab,
    activityLogCollapsed,
    logFilterPreset,
    jobCompleteAt,
    activeSubstepId,
    pipelineCollapsedStages,
    pipelineExpandedDoneStages,
    pipelineFilterNeedsYou,
    setPipelineFilterNeedsYou,
    setActivityLogTab,
    setActivityLogCollapsed,
    setLogFilterPreset,
    pinSelectedStage,
    setActiveTab,
    setPipelineSubTab: setPipelineSubTabWrapped,
    openArtifactInEditor,
    setSelectedAsset,
    setMenuOpen,
    showToast,
    openActionModal,
    closeActionModal,
    clearSession,
    refreshHome,
    startRun,
    openRun,
    retryOpenRun,
    refreshRun,
    selectStage,
    executeJob,
    runNextStage,
    redoFromStage,
    startJobPoll,
    acknowledgeHandoff,
    approveWriteAndContinue,
    onCheckpointContinue,
    setAlertsMuted,
    appendClientLog,
    loadTranscriptReview,
    setTranscriptReview,
    confirm,
    resolveConfirm,
    activateSubstep,
    setActiveSubstepId,
    expandStage,
    collapseStage,
    toggleDoneStageExpanded,
  };

  return (
    <AppContext.Provider value={value}>
      {children}
      <PrecleanOffersBridge
        shown={shownPrecleanOffers}
        setShown={setShownPrecleanOffers}
        runId={runId}
      />
    </AppContext.Provider>
  );
}

const precleanBridge: {
  shown: Set<string>;
  setShown: ((s: Set<string>) => void) | null;
  runId: string | null;
} = { shown: new Set(), setShown: null, runId: null };

export function getPrecleanBridge() {
  return precleanBridge;
}

function PrecleanOffersBridge({
  shown,
  setShown,
  runId,
}: {
  shown: Set<string>;
  setShown: (s: Set<string>) => void;
  runId: string | null;
}) {
  precleanBridge.shown = shown;
  precleanBridge.setShown = setShown;
  precleanBridge.runId = runId;
  return null;
}
