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
  PipelineSubTab,
  RunData,
  RunSummary,
  StageInfo,
  TimelineData,
  TranscriptReviewState,
} from "../types";
import {
  actionSummaryText,
  countPendingActions,
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
  openRun: (runId: string, opts?: { quiet?: boolean }) => Promise<void>;
  refreshRun: () => Promise<void>;
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
  const [shownPrecleanOffers, setShownPrecleanOffers] = useState<Set<string>>(
    () => new Set(),
  );

  const logCountRef = useRef(0);
  const lastNotifiedTsRef = useRef<string | null>(null);
  const lastActionRequiredIdRef = useRef<string | null>(null);
  const jobStatusPrevRef = useRef<string | null>(null);
  const confirmResolveRef = useRef<((ok: boolean) => void) | null>(null);
  const jobPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const userDismissedActionRef = useRef(false);

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
    () => countPendingActions(run, mergedApiGrants()),
    [run, mergedApiGrants],
  );
  const actionSummary = useMemo(
    () => actionSummaryText(run, mergedApiGrants()),
    [run, mergedApiGrants],
  );

  const setActiveTab = useCallback((tab: AppTab) => {
    setActiveTabState(tab);
  }, []);

  const openArtifactInEditor = useCallback((path: string) => {
    setPipelineSubTab("files");
    window.dispatchEvent(new CustomEvent("handoff-open", { detail: { path } }));
  }, []);

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
    const [assetsRes, runsRes, session] = await Promise.all([
      api<{ files: AssetFile[] }>("/api/assets"),
      api<{ runs: RunSummary[] }>("/api/runs"),
      api<{ log?: LogEntry[]; active?: { run_id?: string } | null }>(
        "/api/session",
      ).catch(() => ({ log: [] as LogEntry[], active: null as null })),
    ]);
    setAssets(assetsRes.files);
    setRuns(runsRes.runs);
    setHomeLog(session.log?.slice(-5) || []);
    setServerActiveRunId(session.active?.run_id ?? null);
  }, []);

  const pollLog = useCallback(async () => {
    if (!runId) return;
    try {
      const data = await api<{ entries: LogEntry[] }>(
        `/api/runs/${runId}/log?tail=500`,
      );
      if (data.entries?.length !== logCountRef.current) {
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

  const refreshRun = useCallback(async (): Promise<void> => {
    if (!runId) return;
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
  }, [runId, renderLogWithAlerts]);

  const selectStage = useCallback(
    async (stageId: string) => {
      setSelectedStageId(stageId);
      if (runId) {
        await api("/api/session/active", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: runId, selected_stage_id: stageId }),
        }).catch(() => {});
      }
    },
    [runId],
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

  const startJobPoll = useCallback(() => {
    stopJobPoll();
    if (!runId) return;
    setJobRunning(true);
    jobPollRef.current = setInterval(async () => {
      const job = await api<JobState>(`/api/runs/${runId}/job`);
      if (job.status !== "running" && job.status !== "running_with_warnings") {
        await refreshRun();
        stopJobPoll();
        if (job.status === "awaiting_write_approval" || job.awaiting_write_approval) {
          if (!userDismissedActionRef.current) {
            openActionModal();
            playAttentionPing(alertsMuted);
          }
        }
      }
      await pollLog();
    }, 1200);
  }, [runId, refreshRun, stopJobPoll, pollLog, openActionModal, alertsMuted]);

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
          showToast("A job is already running — watch Logs for progress.");
          startJobPoll();
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
    ],
  );

  const openRun = useCallback(
    async (id: string, opts: { quiet?: boolean; force?: boolean } = {}) => {
      if (runId && id !== runId && !opts.force) {
        showToast("This session is locked to one source. Clear session to open another run.");
        return;
      }
      setRunId(id);
      setActiveTabState("pipeline");
      setPipelineSubTab("stage");
      userDismissedActionRef.current = false;
      await api("/api/session/active", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: id, selected_stage_id: selectedStageId }),
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
      if (!selectedStageId && runData.stages.length) {
        const active = findActiveStage(runData.stages);
        await selectStage(active?.id || runData.stages[0].id);
      } else if (selectedStageId) {
        await selectStage(selectedStageId);
      }
      if (!opts.quiet) appendClientLogInternal(id, `Opened execution ${id}`, "info");
      startJobPoll();
    },
    [selectedStageId, renderLogWithAlerts, selectStage, startJobPoll, runId, showToast],
  );

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
    [appendClientLog, openRun, showToast, runId],
  );

  const clearSession = useCallback(async () => {
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
    setRun(null);
    setTimeline(null);
    setSelectedStageId(null);
    setServerActiveRunId(null);
    setActionModalOpen(false);
    setActiveTabState("start");
    await refreshHome();
  }, [stopJobPoll, refreshHome]);

  const acknowledgeHandoff = useCallback(async () => {
    if (!runId) return;
    const stageId =
      (run ? findHandoffStage(run)?.id : null) || selectedStageId || null;
    if (!stageId) return;
    await api(`/api/runs/${runId}/handoff-ack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage_id: stageId }),
    });
    showToast("Handoff acknowledged.");
    await refreshRun();
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
    await api(`/api/runs/${runId}/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_stage: mapGateToStage(selectedStageId) }),
    });
    await refreshRun();
  }, [selectedStageId, runId, refreshRun, confirm]);

  const loadTranscriptReview = useCallback(async () => {
    if (!runId) return null;
    const data = await api<TranscriptReviewState>(
      `/api/runs/${runId}/transcript-review`,
    );
    setTranscriptReview(data);
    return data;
  }, [runId]);

  useEffect(() => {
    void (async () => {
      const cfg = await api<AppConfig>("/api/config");
      setConfig(cfg);
      const session = await api<{
        server?: { started_at?: string };
        active?: { run_id?: string; selected_stage_id?: string };
        log?: LogEntry[];
      }>("/api/session");
      const startedAt = session.server?.started_at;
      if (startedAt && localStorage.getItem(GUI_SERVER_STARTED_AT_KEY) !== startedAt) {
        localStorage.setItem(GUI_SERVER_STARTED_AT_KEY, startedAt);
      }
      setServerActiveRunId(session.active?.run_id ?? null);
      await refreshHome();
      if (session.log?.length) renderLogWithAlerts(session.log);
      if (session.active?.run_id) {
        setSelectedStageId(session.active.selected_stage_id || null);
        await openRun(session.active.run_id, { quiet: true });
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
    setActiveTab,
    setPipelineSubTab,
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
