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
  refreshHome: () => Promise<void>;
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
  onCheckpointContinue: () => Promise<void>;
  setAlertsMuted: (muted: boolean) => void;
  appendClientLog: (message: string, level?: string) => void;
  loadTranscriptReview: () => Promise<TranscriptReviewState | null>;
  setTranscriptReview: (data: TranscriptReviewState | null) => void;
  confirm: (message: string) => Promise<boolean>;
  resolveConfirm: (ok: boolean) => void;
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

  const logCountRef = useRef(0);
  const bootGenRef = useRef(0);
  const persistUiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runIdRef = useRef<string | null>(null);
  const selectedStageIdRef = useRef<string | null>(null);
  const activeTabRef = useRef<AppTab>("start");
  const pipelineSubTabRef = useRef<PipelineSubTab>("stage");
  const activityLogTabRef = useRef<LogStreamTab>("live");
  const activityLogCollapsedRef = useRef(false);
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
    window.setTimeout(() => setToast(null), 3500);
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
        }),
      }).catch(() => {});
    }, 200);
  }, []);

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

  const refreshHome = useCallback(async () => {
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

    await Promise.allSettled([
      track(
        api<{ files?: AssetFile[] }>("/api/assets"),
        (data) => setAssets(data.files ?? []),
        "Source audio",
      ),
      track(
        api<{ runs?: RunSummary[] }>("/api/runs?enrich=1&enrich_limit=50"),
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
          showToast(res.error || "Failed to start");
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
        startJobPoll();
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          showToast(
            e.message ||
              "A job is already running — watch Logs for progress, or refresh after a server restart.",
          );
          const job = runId ? await syncJobRunning(runId) : null;
          if (isJobActivelyRunning(job)) startJobPoll();
          else await refreshRun();
          return;
        }
        showToast(e instanceof Error ? e.message : "Failed to start job");
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

  const appendClientLogInternal = async (
    rid: string | null,
    message: string,
    level = "info",
  ) => {
    if (!rid) {
      renderLogWithAlerts([
        { ts: new Date().toISOString(), level: level as LogEntry["level"], message },
      ]);
      return;
    }
    await api(`/api/runs/${rid}/log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, level }),
    });
    await pollLog();
  };

  const appendClientLog = useCallback(
    (message: string, level = "info") => {
      void appendClientLogInternal(runId, message, level);
    },
    [runId],
  );

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
    try {
      await api(`/api/runs/${runId}/handoff-ack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage_id: stageId }),
      });
      showToast("Handoff acknowledged.");
      await refreshRun();
    } catch (e) {
      showToast(e instanceof ApiError ? e.message : "Handoff acknowledgment failed");
    }
  }, [selectedStageId, runId, run, showToast, refreshRun]);

  const runNextStage = useCallback(async () => {
    if (!run) return;
    if (run.job?.status === "awaiting_write_approval" || run.job?.awaiting_write_approval) {
      const sid = run.job.pending_write_stage || run.job.stage;
      if (sid) await selectStage(sid);
      openActionModal();
      showToast("Review stage outputs before saving to disk.");
      return;
    }
    const handoffStage = findHandoffStage(run);
    if (handoffStage) {
      showToast(
        `Review outputs from ${handoffStage.title} on the Pipeline tab, then acknowledge to continue.`,
      );
      await selectStage(handoffStage.id);
      return;
    }
    if (hasActionRequiredStage(run.stages)) {
      const blocked = run.stages.find((s) => s.status === "action_required");
      showToast(
        `Complete checkpoint: ${blocked?.title || "action required"} before running.`,
      );
      if (blocked) await selectStage(blocked.id);
      openActionModal();
      playAttentionPing(alertsMuted);
      return;
    }
    const next = findNextRunnableStage(run.stages);
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
      openActionModal();
      return;
    }
    await executeJob({ mode: "stage", stage: next.id });
  }, [run, alertsMuted, showToast, selectStage, executeJob, openActionModal]);

  const onCheckpointContinue = useCallback(async () => {
    if (!run || !selectedStage) return;
    const paths = getHandoffPathsLocal(selectedStage, run.log_tail);
    if (selectedStage.status === "done" && paths.length) {
      await acknowledgeHandoff();
      setActionModalOpen(false);
      return;
    }
    if (selectedStage.id === "g1_vo_pickup" && run.g1_clear) {
      await selectStage("g2_flow_select");
      return;
    }
    await runNextStage();
  }, [run, selectedStage, acknowledgeHandoff, selectStage, runNextStage]);

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
        const serverRestarted = Boolean(startedAt && prevStarted && startedAt !== prevStarted);
        if (startedAt) localStorage.setItem(GUI_SERVER_STARTED_AT_KEY, startedAt);
        setServerActiveRunId(session.active?.run_id ?? null);
        await refreshHome();
        if (gen !== bootGenRef.current) return;
        if (session.log?.length) renderLogWithAlerts(session.log);
        const active = session.active;
        if (active?.run_id) {
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
          if (gen !== bootGenRef.current) return;
          if (serverRestarted && runIdRef.current) {
            const rid = runIdRef.current;
            await syncJobRunning(rid);
            const runData = await api<RunData>(`/api/runs/${rid}`);
            setRun(runData);
            renderLogWithAlerts(runData.log_tail || []);
          }
        }
      } catch (e) {
        if (gen !== bootGenRef.current) return;
        const msg = e instanceof Error ? e.message : "Failed to load session";
        setSessionLoadError(msg);
        showToast(msg);
      } finally {
        if (gen === bootGenRef.current) setSessionReady(true);
      }
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
    }
  }, [pendingActionCount]);

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
    onCheckpointContinue,
    setAlertsMuted,
    appendClientLog,
    loadTranscriptReview,
    setTranscriptReview,
    confirm,
    resolveConfirm,
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
