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
  ToastLevel,
  ToastState,
} from "../types";
import { formatApiError } from "../utils/safeApi";
import { isJobActivelyRunning } from "../utils/jobStatus";
import { isOperatorGateStartResponse } from "../utils/jobStartResponse";
import { countRequiredAttention, stageNeedsAttention } from "../utils/attentionQueue";
import { maybePingForRequiredAttention } from "../utils/attentionPing";
import { resolveOperatorAction } from "../utils/resolveOperatorAction";
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
  resolvePrecleanOffer,
} from "../utils/preclean";
import { pendingWriteInfo, resolvePendingWritePaths, stageAwaitingWriteApproval } from "../utils/writeApproval";
import { runStepPrimaryPrep, runStepPrimaryPreps } from "../utils/stepPrimaryPrep";
import { describeExecuteBody } from "../utils/operatorActionLog";
import { guardBusy } from "../utils/guardBusy";
import { jobCompletionHint } from "../utils/jobCompletionHints";
import { executeBodyForStage } from "../utils/operatorActionHandlers";
import { scrollToStageStep } from "../utils/activateStageStep";
import {
  advancePipeline,
  focusStageWorkbench,
  patchRunAfterWriteApproval,
  reconcileBusyRun,
  syncPipelineStageFocus,
  tryAutoContinuePipeline,
  type AdvancePipelineOpts,
  type ExecuteJobSource,
} from "../utils/checkpointContinuation";
import {
  canAutoRunStage,
  isPipelineAutopilotEnabled,
} from "../utils/pipelineAutopilot";
import {
  focusNextRunnableStageWorkbench,
  handleReuseFromAssetsForStage,
  readyForStageMessage,
} from "../utils/stageAdvance";
import { recordAutoContinue, shouldSkipDuplicateAutoContinue } from "../utils/autoContinueDedupe";
import { shouldSuppressJobPollTerminalToast } from "../utils/jobPollToasts";
import { substepIdToStepId } from "../utils/resolveActiveStep";
import {
  clampPipelineSubTab,
  pipelineSubTabAvailability,
} from "../utils/pipelineSubTabAvailability";
import { navigatePipelineSubTab as navigatePipelineSubTabUtil } from "../utils/navigatePipelineSubTab";
import { setRunState, bumpLocalVersion } from "./runStateStore";
import { JobProvider } from "./providers/JobProvider";
import { RunProvider } from "./providers/RunProvider";
import { SessionProvider } from "./providers/SessionProvider";
import type { StageSubstep } from "../types";
import { prefetchTab } from "../components/tabs/lazyTabs";

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
  toast: ToastState | null;
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
  activeStepId: string | null;
  setActiveStepId: (stepId: string | null) => void;
  pipelineCollapsedStages: string[];
  pipelineExpandedDoneStages: string[];
  pipelineFilterNeedsYou: boolean;
  isStagePinned: boolean;
  setActivityLogTab: (tab: LogStreamTab) => void;
  setActivityLogCollapsed: (collapsed: boolean) => void;
  setLogFilterPreset: (preset: LogFilterPreset | null) => void;
  pinSelectedStage: () => void;
  setActiveTab: (tab: AppTab) => void;
  setPipelineSubTab: (tab: PipelineSubTab) => void;
  navigatePipelineSubTab: (tab: PipelineSubTab, opts?: { force?: boolean }) => void;
  openArtifactInEditor: (path: string) => void;
  setSelectedAsset: (path: string | null) => void;
  setMenuOpen: (open: boolean) => void;
  showToast: (msg: string, level?: ToastLevel) => void;
  dismissToast: () => void;
  openActionModal: () => void;
  closeActionModal: () => void;
  closeActionModalAfterSuccess: () => void;
  clearSession: () => Promise<void>;
  refreshHome: (opts?: { enrichRuns?: boolean }) => Promise<void>;
  startRun: (inputPath: string, flowIntent?: string) => Promise<void>;
  openRun: (runId: string, opts?: OpenRunOptions) => Promise<void>;
  retryOpenRun: () => Promise<void>;
  refreshRun: () => Promise<RunData | null>;
  selectStage: (stageId: string, opts?: { pinned?: boolean; stepId?: string | null }) => Promise<void>;
  executeJob: (body: ExecuteBody, opts?: { source?: ExecuteJobSource }) => Promise<void>;
  beginStageExecution: (opts: {
    kind: "execute" | "decline_reuse_and_run";
    stageId: string;
    body?: ExecuteBody;
  }) => Promise<boolean>;
  runNextStage: () => Promise<void>;
  redoFromStage: () => Promise<void>;
  startJobPoll: () => void;
  acknowledgeHandoff: () => Promise<void>;
  approveWriteAndContinue: (stageId?: string) => Promise<boolean>;
  fixAllAndContinueStage: (stageId: string) => Promise<boolean>;
  revalidateArtifactIssues: (stageId: string) => Promise<void>;
  discardPendingWrites: (stageId: string) => Promise<void>;
  completeTranscriptReview: (acceptUnreviewed?: boolean) => Promise<void>;
  completeDisfluencyReview: (acceptUnreviewed?: boolean) => Promise<void>;
  approveSfxPrompts: () => Promise<void>;
  advanceFromCheckpoint: () => Promise<void>;
  autoContinuePipeline: (completedStageId?: string | null) => Promise<boolean>;
  syncPipelineStageFocus: (runOverride?: RunData | null) => Promise<boolean>;
  onCheckpointContinue: () => Promise<void>;
  setCheckpointBusy: (busy: boolean) => void;
  setAlertsMuted: (muted: boolean) => void;
  appendClientLog: (message: string, level?: string, stage?: string, actionId?: string) => void;
  traceAction: (actionId: string, message: string, opts?: { level?: string; stage?: string }) => void;
  dumpLastStep: () => Promise<void>;
  loadTranscriptReview: () => Promise<TranscriptReviewState | null>;
  setTranscriptReview: (data: TranscriptReviewState | null) => void;
  confirm: (message: string) => Promise<boolean>;
  resolveConfirm: (ok: boolean) => void;
  activateSubstep: (substep: StageSubstep) => void;
  setActiveSubstepId: (id: string | null) => void;
  skipOptionalStage: (stageId: string) => Promise<void>;
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
  const [toast, setToast] = useState<ToastState | null>(null);
  const [jobRunning, setJobRunning] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const jobRunningRef = useRef(false);
  const actionBusyRef = useRef(false);
  const approveInFlightRef = useRef(false);
  const autopilotInFlightRef = useRef(false);
  const acknowledgeHandoffRef = useRef<() => Promise<void>>(async () => {});
  const autoContinuePipelineRef = useRef<(completedStageId?: string | null) => Promise<boolean>>(
    async () => false,
  );
  const syncPipelineStageFocusRef = useRef<(runOverride?: RunData | null) => Promise<boolean>>(
    async () => false,
  );
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
  const [activityLogTab, setActivityLogTabState] = useState<LogStreamTab>("all");
  const [activityLogCollapsed, setActivityLogCollapsedState] = useState(false);
  const [logFilterPreset, setLogFilterPresetState] = useState<LogFilterPreset | null>(
    null,
  );
  const [jobCompleteAt, setJobCompleteAt] = useState<number | null>(null);
  const [activeSubstepId, setActiveSubstepIdState] = useState<string | null>(null);
  const [activeStepId, setActiveStepIdState] = useState<string | null>(null);
  const [pipelineCollapsedStages, setPipelineCollapsedStages] = useState<string[]>([]);
  const [pipelineExpandedDoneStages, setPipelineExpandedDoneStages] = useState<string[]>(
    [],
  );
  const [pipelineFilterNeedsYou, setPipelineFilterNeedsYouState] = useState(true);
  const [pinnedStageId, setPinnedStageId] = useState<string | null>(null);

  const logCountRef = useRef(0);
  const recentClientLogRef = useRef<{ key: string; at: number } | null>(null);
  const bootGenRef = useRef(0);
  const persistUiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runIdRef = useRef<string | null>(null);
  const selectedStageIdRef = useRef<string | null>(null);
  const activeTabRef = useRef<AppTab>("start");
  const activeStepIdRef = useRef<string | null>(null);
  const pipelineSubTabRef = useRef<PipelineSubTab>("stage");
  const activityLogTabRef = useRef<LogStreamTab>("all");
  const activityLogCollapsedRef = useRef(false);
  const pipelineCollapsedRef = useRef<string[]>([]);
  const pipelineExpandedDoneRef = useRef<string[]>([]);
  const pipelineFilterNeedsYouRef = useRef(true);
  const lastAttentionPingKeyRef = useRef("");
  const confirmResolveRef = useRef<((ok: boolean) => void) | null>(null);
  const jobPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const userDismissedActionRef = useRef(false);
  const lastAutoOpenKeyRef = useRef<string | null>(null);
  const lastDismissedFocusKeyRef = useRef<string | null>(null);
  const userPinnedStageIdRef = useRef<string | null>(null);
  const runRefreshTickRef = useRef(0);

  const selectedStage = useMemo(
    () => run?.stages.find((s) => s.id === selectedStageId),
    [run, selectedStageId],
  );

  const dismissToast = useCallback(() => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = null;
    setToast(null);
  }, []);

  const showToast = useCallback((msg: string, level: ToastLevel = "info") => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ message: msg, level });
    const extended = jobRunningRef.current || actionBusyRef.current;
    toastTimerRef.current = window.setTimeout(
      () => setToast(null),
      extended ? 7000 : level === "error" ? 6000 : 3500,
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
    const sid = selectedStageIdRef.current;
    if (!sid) return;
    userPinnedStageIdRef.current = sid;
    setPinnedStageId(sid);
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
          active_step_id: activeStepIdRef.current,
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
      prefetchTab(tab);
      setActiveTabState(tab);
      activeTabRef.current = tab;
      persistSessionUi();
    },
    [persistSessionUi],
  );

  const setPipelineSubTabWrapped = useCallback(
    (tab: PipelineSubTab, opts?: { force?: boolean }) => {
      navigatePipelineSubTabUtil(tab, run, timeline, {
        force: opts?.force,
        onBlocked: (reason) => showToast(reason, "warning"),
        onNavigate: (next) => {
          setPipelineSubTab(next);
          pipelineSubTabRef.current = next;
          persistSessionUi();
        },
      });
    },
    [persistSessionUi, run, timeline, showToast],
  );

  const navigatePipelineSubTab = setPipelineSubTabWrapped;

  const openArtifactInEditor = useCallback(
    (path: string) => {
      setPipelineSubTabWrapped("files");
      window.dispatchEvent(new CustomEvent("handoff-open", { detail: { path } }));
    },
    [setPipelineSubTabWrapped],
  );

  const closeActionModal = useCallback(() => {
    /* checkpoint modals removed — workbench is inline */
  }, []);

  const closeActionModalAfterSuccess = useCallback(() => {
    /* no-op */
  }, []);

  const setCheckpointBusy = useCallback((busy: boolean) => {
    setActionBusy(busy);
    actionBusyRef.current = busy;
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

  const renderLogWithAlerts = useCallback((entries: LogEntry[]) => {
    setLogEntries(entries);
    logCountRef.current = entries.length;
  }, []);

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
    if (errors.length) showToast(errors.join(" · "), "error");
  }, [showToast]);

  const pollLog = useCallback(async (force?: boolean) => {
    if (!runId) return;
    try {
      const data = await api<{ entries: LogEntry[] }>(
        `/api/runs/${runId}/log?tail=500`,
      );
      if (force || data.entries?.length !== logCountRef.current) {
        renderLogWithAlerts(data.entries);
        setRun((prev) => {
          if (!prev) return prev;
          const prevTail = prev.log_tail;
          if (
            prevTail?.length === data.entries?.length &&
            prevTail?.[prevTail.length - 1]?.ts === data.entries?.[data.entries.length - 1]?.ts
          ) {
            return prev;
          }
          return { ...prev, log_tail: data.entries };
        });
      }
    } catch (reason) {
      showToast(formatApiError(reason, "Activity log"), "error");
    }
  }, [runId, renderLogWithAlerts, showToast]);

  const appendClientLogInternal = async (
    rid: string | null,
    message: string,
    level = "info",
    stage?: string,
    actionId?: string,
  ) => {
    const dedupeKey = actionId || `${level}:${message}`;
    const now = Date.now();
    if (level !== "error" && level !== "action") {
      const recent = recentClientLogRef.current;
      if (recent && recent.key === dedupeKey && now - recent.at < 5_000) {
        return;
      }
    }
    recentClientLogRef.current = { key: dedupeKey, at: now };

    if (!rid) {
      renderLogWithAlerts([
        {
          ts: new Date().toISOString(),
          level: level as LogEntry["level"],
          message,
          stage,
          detail: actionId ? { action_id: actionId, origin: "gui" } : undefined,
        },
      ]);
      return;
    }
    await api(`/api/runs/${rid}/log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, level, stage, action_id: actionId }),
    });
    await pollLog();
  };

  const appendClientLog = useCallback(
    (message: string, level = "info", stage?: string, actionId?: string) => {
      void appendClientLogInternal(runId, message, level, stage, actionId);
    },
    [runId, pollLog],
  );

  const traceAction = useCallback(
    (
      actionId: string,
      message: string,
      opts?: { level?: string; stage?: string },
    ) => {
      const level = opts?.level ?? "info";
      const stage = opts?.stage || selectedStageIdRef.current || undefined;
      void appendClientLogInternal(runId, message, level, stage, actionId);
    },
    [runId, pollLog],
  );

  const logOperatorAction = useCallback(
    (message: string, stage?: string | null) => {
      traceAction("gui.operator.action", message, {
        level: "action",
        stage: stage || selectedStageIdRef.current || undefined,
      });
    },
    [traceAction],
  );

  const dumpLastStep = useCallback(async () => {
    if (!runId) {
      showToast("No active run for action trace.");
      return;
    }
    try {
      const { dumpLastAction } = await import("../api/actionTrace");
      const { formatClientTraceDump } = await import("../utils/operatorActionTrace");
      const serverText = await dumpLastAction(runId);
      const clientText = formatClientTraceDump();
      const combined = [serverText, clientText].filter(Boolean).join("\n\n");
      if (combined) {
        traceAction("gui.activity.dump_last", combined, { level: "info" });
      }
      showToast("Last action trace printed to log.");
      await pollLog(true);
    } catch (reason) {
      showToast(formatApiError(reason, "Dump last step"), "error");
    }
  }, [runId, showToast, traceAction, pollLog]);

  const stopJobPoll = useCallback(() => {
    if (jobPollRef.current) {
      clearInterval(jobPollRef.current);
      jobPollRef.current = null;
    }
    jobPollSawRunningRef.current = false;
    setJobRunning(false);
  }, []);

  const refreshRun = useCallback(async (): Promise<RunData | null> => {
    if (!runId) return null;
    try {
      const runData = await api<RunData>(`/api/runs/${runId}`);
      setRun(runData);
      setRunState(runData);
      setShownPrecleanOffers(
        new Set(runData.meta?.audio_preclean?.offered_at || []),
      );
      const tl = await api<TimelineData>(`/api/runs/${runId}/timeline`).catch(
        () => null,
      );
      setTimeline(tl);
      renderLogWithAlerts(runData.log_tail || []);
      return runData;
    } catch (reason) {
      showToast(formatApiError(reason, "Refresh run"), "error");
      return null;
    }
  }, [runId, renderLogWithAlerts, showToast]);

  const setActiveStepId = useCallback(
    (stepId: string | null) => {
      setActiveStepIdState(stepId);
      activeStepIdRef.current = stepId;
      persistSessionUi();
    },
    [persistSessionUi],
  );

  const selectStage = useCallback(
    async (stageId: string, opts?: { pinned?: boolean; stepId?: string | null }) => {
      if (opts?.pinned !== false) {
        userPinnedStageIdRef.current = stageId;
        setPinnedStageId(stageId);
      }
      const sameStage = selectedStageIdRef.current === stageId;
      setSelectedStageId(stageId);
      selectedStageIdRef.current = stageId;
      if (opts?.stepId !== undefined) {
        setActiveStepIdState(opts.stepId);
        activeStepIdRef.current = opts.stepId;
      } else if (!sameStage) {
        setActiveStepIdState(null);
        activeStepIdRef.current = null;
      }
      persistSessionUi();
    },
    [persistSessionUi],
  );

  const maybeAutoSelectRunningStage = useCallback(
    (job: JobState | null | undefined) => {
      if (!job || !isJobActivelyRunning(job)) return;
      const stageId = job.current_stage || job.stage;
      if (!stageId) return;
      const pinnedSid = userPinnedStageIdRef.current;
      if (pinnedSid && pinnedSid !== stageId) return;
      if (selectedStageIdRef.current === stageId) return;
      setSelectedStageId(stageId);
      selectedStageIdRef.current = stageId;
      setActiveStepIdState(null);
      activeStepIdRef.current = null;
    },
    [],
  );

  const focusPendingStage = useCallback(
    async (runOverride?: RunData | null) => {
      await syncPipelineStageFocusRef.current(runOverride);
    },
    [],
  );

  const openActionModal = useCallback(() => {
    void focusPendingStage();
    setActiveTabState("pipeline");
    setPipelineSubTabWrapped("stage");
  }, [focusPendingStage, setPipelineSubTabWrapped]);

  const pipelineFocusKey = run
    ? [
        run.job?.status ?? "",
        run.job?.stage ?? "",
        run.journey?.blocking?.reason ?? "",
        run.journey?.blocking?.stage_id ?? "",
        findPendingFocusStage(run, ALL_API_CONSENTS) ?? "",
        run.stages.map((s) => `${s.id}:${s.status}`).join("|"),
        run.handoff_ack ? Object.keys(run.handoff_ack).sort().join(",") : "",
      ].join(":")
    : "";

  useEffect(() => {
    if (!run || activeTabRef.current !== "pipeline") return;
    const needsFilter =
      run.stages.some(
        (s) => s.status === "action_required" || s.status === "awaiting_write_approval",
      ) ||
      Boolean(run.journey?.blocking?.blocked) ||
      Boolean(run.job?.needs_stage_reuse);
    if (needsFilter && !pipelineFilterNeedsYouRef.current) {
      setPipelineFilterNeedsYouState(true);
      pipelineFilterNeedsYouRef.current = true;
    }
  }, [pipelineFocusKey, run]);

  useEffect(() => {
    if (!run || activeTabRef.current !== "pipeline" || jobRunning) return;
    if (autopilotInFlightRef.current || actionBusyRef.current || approveInFlightRef.current) {
      return;
    }
    const focusId = findPendingFocusStage(run, ALL_API_CONSENTS);
    const currentId = selectedStageIdRef.current;
    if (!focusId || focusId === currentId) return;
    if (currentId && stageNeedsAttention(run, currentId, ALL_API_CONSENTS)) return;
    void syncPipelineStageFocusRef.current();
  }, [pipelineFocusKey, jobRunning, run]);

  const syncJobRunning = useCallback(async (rid: string) => {
    try {
      const job = await api<JobState>(`/api/runs/${rid}/job`);
      const active = isJobActivelyRunning(job);
      setJobRunning(active);
      setRun((prev) => (prev ? { ...prev, job } : prev));
      maybeAutoSelectRunningStage(job);
      return job;
    } catch (reason) {
      setJobRunning(false);
      showToast(formatApiError(reason, "Job status"), "error");
      return null;
    }
  }, [maybeAutoSelectRunningStage, showToast]);

  const jobPollStatusRef = useRef<string | null>(null);
  const jobPollSawRunningRef = useRef(false);
  const autoContinueDedupeRef = useRef<{ stageId: string; at: number } | null>(null);

  const startJobPoll = useCallback(() => {
    stopJobPoll();
    if (!runId) return;
    void (async () => {
      const job = await syncJobRunning(runId);
      if (!isJobActivelyRunning(job)) return;
      jobPollSawRunningRef.current = true;
      setJobRunning(true);
      runRefreshTickRef.current = 0;
      jobPollRef.current = setInterval(async () => {
        try {
          const polled = await api<JobState>(`/api/runs/${runId}/job`);
          const prevStatus = jobPollStatusRef.current;
          jobPollStatusRef.current = polled.status ?? null;
          if (isJobActivelyRunning(polled)) {
            jobPollSawRunningRef.current = true;
          }
          setRun((prev) => (prev ? { ...prev, job: polled } : prev));
          maybeAutoSelectRunningStage(polled);
          if (!isJobActivelyRunning(polled)) {
            const refreshed = await refreshRun();
            const suppressTerminalToast = shouldSuppressJobPollTerminalToast(
              jobPollSawRunningRef.current,
              polled,
            );
            stopJobPoll();
            setActionBusy(false);
            actionBusyRef.current = false;
            approveInFlightRef.current = false;
            void focusPendingStage(refreshed);
            setActivityLogTabState("live");
            activityLogTabRef.current = "live";
            if (!suppressTerminalToast) {
              if (polled.status === "complete") {
                setJobCompleteAt(Date.now());
                const next = refreshed?.journey?.next_action;
                const completedStage =
                  polled.current_stage || polled.stage || undefined;
                const stageHint = jobCompletionHint(completedStage, refreshed);
                showToast(
                  stageHint
                    ? `Step finished — ${stageHint}`
                    : next
                      ? `Step finished — ${next}`
                      : "Step finished.",
                  "success",
                );
                if (next && runId) {
                  void api(`/api/runs/${runId}/log`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      message: `Step finished — next: ${next}`,
                      level: "info",
                    }),
                  }).then(() => pollLog());
                }
                void autoContinuePipelineRef.current(completedStage ?? null);
              } else if (polled.status === "error") {
                showToast(
                  polled.last_error?.message || polled.message || "Step failed",
                  "error",
                );
              } else if (
                polled.status === "gate" ||
                polled.status === "needs_operator"
              ) {
                showToast(
                  "Paused for your review — complete the checkpoint to continue.",
                  "info",
                );
                userDismissedActionRef.current = false;
                lastAutoOpenKeyRef.current = null;
                if (activeTabRef.current === "pipeline") {
                  setActionModalOpen(true);
                }
              }
              if (
                polled.status === "awaiting_write_approval" ||
                polled.awaiting_write_approval
              ) {
                showToast("Review staged outputs before continuing.", "info");
                const sid = polled.pending_write_stage || polled.stage;
                if (sid) {
                  void selectStage(sid);
                  expandStage(sid);
                }
                userDismissedActionRef.current = false;
                lastAutoOpenKeyRef.current = null;
                if (activeTabRef.current === "pipeline") {
                  setActionModalOpen(true);
                }
              } else if (
                polled.status !== "gate" &&
                polled.status !== "needs_operator"
              ) {
                const focusId = refreshed
                  ? resolveOperatorAction(refreshed, {
                      selectedStageId: selectedStageIdRef.current,
                      jobRunning: false,
                      apiGrants: ALL_API_CONSENTS,
                    }).stageId
                  : null;
                if (focusId) expandStage(focusId);
              }
            } else if (polled.status === "complete") {
              const completedStage =
                polled.current_stage || polled.stage || undefined;
              void autoContinuePipelineRef.current(completedStage ?? null);
            }
          } else {
            runRefreshTickRef.current += 1;
            const statusChanged = prevStatus !== polled.status;
            if (statusChanged || runRefreshTickRef.current % 5 === 0) {
              await refreshRun();
            }
          }
          await pollLog(true);
        } catch (reason) {
          stopJobPoll();
          showToast(formatApiError(reason, "Job poll"), "error");
        }
      }, 1000);
    })();
  }, [
    runId,
    refreshRun,
    stopJobPoll,
    pollLog,
    openActionModal,
    syncJobRunning,
    maybeAutoSelectRunningStage,
    focusPendingStage,
    showToast,
    pollLog,
  ]);

  const markJobStarting = useCallback(
    (stageId: string, message?: string) => {
      const optimisticJob: JobState = {
        status: "running",
        stage: stageId,
        current_stage: stageId,
        message: message || `Starting ${stageId.replace(/_/g, " ")}…`,
      };
      setJobRunning(true);
      setRun((prev) => (prev ? { ...prev, job: optimisticJob } : prev));
      setActivityLogTabState("live");
      activityLogTabRef.current = "live";
      setActivityLogCollapsedState(false);
      activityLogCollapsedRef.current = false;
      expandStage(stageId);
    },
    [expandStage],
  );

  const handleJobStartResponse = useCallback(
    async (
      res: {
        ok?: boolean;
        error?: string;
        needs_stage_reuse?: boolean;
        stage?: string;
        awaiting_write_approval?: boolean;
        pending_write_stage?: string;
        job?: JobState;
      },
      stageForLog?: string,
    ): Promise<boolean> => {
      if (res.ok === false) {
        setJobRunning(false);
        const operatorGate = isOperatorGateStartResponse(res);
        if (operatorGate) {
          appendClientLog(res.error || "Paused for your review", "info", stageForLog);
        } else {
          appendClientLog(res.error || "Failed to start job", "error", stageForLog);
          showToast(res.error || "Failed to start", "error");
        }
        const busyJob = res.job;
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
          expandStage(res.stage);
          await refreshRun();
          return false;
        }
        if (res.awaiting_write_approval && res.pending_write_stage) {
          await selectStage(res.pending_write_stage);
          expandStage(res.pending_write_stage);
          await refreshRun();
          return false;
        }
        await refreshRun();
        return false;
      }
      appendClientLog("Pipeline job started — streaming logs below.", "info", stageForLog);
      await pollLog(true);
      startJobPoll();
      return true;
    },
    [
      showToast,
      refreshRun,
      startJobPoll,
      selectStage,
      openActionModal,
      appendClientLog,
      pollLog,
    ],
  );

  const beginStageExecution = useCallback(
    async (opts: {
      kind: "execute" | "decline_reuse_and_run";
      stageId: string;
      body?: ExecuteBody;
    }): Promise<boolean> => {
      if (!runId) return false;
      if (jobRunningRef.current) {
        showToast("A step is already running — watch the activity log.", "warning");
        return false;
      }
      if (actionBusyRef.current) {
        showToast("Checkpoint save in progress — watch Activity (Live).", "warning");
        return false;
      }
      const { stageId, kind, body } = opts;
      const handoffStage = findHandoffStage(run);
      if (handoffStage) {
        showToast(
          `Review outputs from ${handoffStage.title} on the Pipeline tab, then acknowledge to continue.`,
        );
        await selectStage(handoffStage.id);
        return false;
      }
      const label =
        kind === "decline_reuse_and_run"
          ? `Run fresh — ${stageId.replace(/_/g, " ")}`
          : describeExecuteBody(body || { mode: "stage", stage: stageId });
      logOperatorAction(label, stageId);
      markJobStarting(
        stageId,
        kind === "decline_reuse_and_run" ? `Running ${stageId.replace(/_/g, " ")} fresh…` : undefined,
      );
      try {
        const res =
          kind === "decline_reuse_and_run"
            ? await api<{
                ok?: boolean;
                error?: string;
                needs_stage_reuse?: boolean;
                stage?: string;
                awaiting_write_approval?: boolean;
                pending_write_stage?: string;
                job?: JobState;
              }>(`/api/runs/${runId}/stages/${stageId}/reuse`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  action: "decline_and_run",
                  api_consents: ALL_API_CONSENTS,
                }),
              })
            : await api<{
                ok?: boolean;
                error?: string;
                needs_stage_reuse?: boolean;
                stage?: string;
                awaiting_write_approval?: boolean;
                pending_write_stage?: string;
                job?: JobState;
              }>(`/api/runs/${runId}/execute`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  ...(body || { mode: "stage", stage: stageId }),
                  api_consents: ALL_API_CONSENTS,
                }),
              });
        return handleJobStartResponse(res, stageId);
      } catch (e) {
        setJobRunning(false);
        if (e instanceof ApiError && e.status === 409) {
          const { jobRunning: busy } = await reconcileBusyRun({
            runId,
            syncJobRunning,
            refreshRun,
            startJobPoll,
            setActivityLogTab: setActivityLogTabState,
            showToast,
            context: "execute",
          });
          if (!busy) {
            await refreshRun();
          }
          return false;
        }
        const msg = formatApiError(e, "Start job");
        appendClientLog(msg, "error", stageId);
        showToast(msg, "error");
        await refreshRun();
        return false;
      }
    },
    [
      runId,
      run,
      showToast,
      selectStage,
      logOperatorAction,
      markJobStarting,
      handleJobStartResponse,
      syncJobRunning,
      startJobPoll,
      refreshRun,
      appendClientLog,
    ],
  );

  const executeJob = useCallback(
    async (body: ExecuteBody, opts?: { source?: ExecuteJobSource }) => {
      const fromCheckpoint = opts?.source === "checkpoint_continue";
      if (jobRunningRef.current) {
        showToast("A step is already running — watch the activity log.", "warning");
        return;
      }
      if (actionBusyRef.current && !fromCheckpoint) {
        showToast("Checkpoint save in progress — watch Activity (Live).", "warning");
        return;
      }
      const stageForLog = body.stage || body.from_stage;
      if (!stageForLog) {
        if (!runId) return;
        const handoffStage = findHandoffStage(run);
        if (handoffStage) {
          showToast(
            `Review outputs from ${handoffStage.title} on the Pipeline tab, then acknowledge to continue.`,
          );
          await selectStage(handoffStage.id);
          return;
        }
        logOperatorAction(describeExecuteBody(body));
        markJobStarting(body.mode);
        try {
          const res = await api(`/api/runs/${runId}/execute`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...body, api_consents: ALL_API_CONSENTS }),
          });
          await handleJobStartResponse(res as { ok?: boolean }, body.mode);
        } catch (e) {
          setJobRunning(false);
          const msg = formatApiError(e, "Start job");
          appendClientLog(msg, "error");
          showToast(msg, "error");
        }
        return;
      }
      if (fromCheckpoint && findHandoffStage(run)) {
        await acknowledgeHandoffRef.current();
        return;
      }
      await beginStageExecution({ kind: "execute", stageId: stageForLog, body });
    },
    [
      runId,
      run,
      showToast,
      selectStage,
      logOperatorAction,
      markJobStarting,
      handleJobStartResponse,
      beginStageExecution,
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
      prefetchTab(tab);
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
        setRunState(runData);
        setShownPrecleanOffers(
          new Set(runData.meta?.audio_preclean?.offered_at || []),
        );
        const tl = await api<TimelineData>(`/api/runs/${id}/timeline`).catch(
          () => null,
        );
        setTimeline(tl);
        const clampedSubTab = clampPipelineSubTab(subTab, runData, tl);
        if (clampedSubTab !== subTab) {
          setPipelineSubTab(clampedSubTab);
          pipelineSubTabRef.current = clampedSubTab;
          await api("/api/session/active", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              run_id: id,
              selected_stage_id: stageId,
              active_tab: tab,
              pipeline_sub_tab: clampedSubTab,
            }),
          });
        }
        renderLogWithAlerts(runData.log_tail || []);
        const resolvedStage =
          stageId ||
          findActiveStage(runData.stages, runData.meta)?.id ||
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
        showToast(msg, "error");
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
        showToast("Creating execution…", "info");
        const res = await api<{ run_id: string }>("/api/runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        appendClientLog(`Created execution ${res.run_id}`, "success");
        await openRun(res.run_id);
      } catch (e) {
        showToast(e instanceof Error ? e.message : "Failed to start run", "error");
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
    setActiveTabState("start");
    activeTabRef.current = "start";
    await refreshHome();
  }, [stopJobPoll, refreshHome, sessionReady]);

  const runNextStage = useCallback(async () => {
    const current = runId ? await refreshRun() : run;
    if (!current) return;
    const write = pendingWriteInfo(current);
    if (write?.paths.length) {
      await focusStageWorkbench({
        run: current,
        stageId: write.stageId,
        selectStage,
        expandStage,
        setActiveStepId,
        setPipelineSubTab: setPipelineSubTabWrapped,
        blockingReason: "write_approval",
      });
      return;
    }
    if (
      current.job?.status === "awaiting_write_approval" ||
      current.job?.awaiting_write_approval
    ) {
      const sid = current.job.pending_write_stage || current.job.stage;
      if (sid) {
        await focusStageWorkbench({
          run: current,
          stageId: sid,
          selectStage,
          expandStage,
          setActiveStepId,
          setPipelineSubTab: setPipelineSubTabWrapped,
          blockingReason: "write_approval",
        });
      }
      return;
    }
    const blocking = current.journey?.blocking ?? current.blocking;
    if (blocking?.blocked && blocking.stage_id) {
      const sid = blocking.stage_id;
      const substepId =
        blocking.reason === "stage_reuse"
          ? `stage_reuse:${sid}`
          : blocking.reason === "handoff_review"
            ? `handoff:${sid}`
            : blocking.reason === "write_approval"
              ? `write_approval:${sid}`
              : null;
      await focusStageWorkbench({
        run: current,
        stageId: sid,
        selectStage,
        expandStage,
        setActiveStepId,
        setPipelineSubTab: setPipelineSubTabWrapped,
        substepId,
        blockingReason: blocking.reason,
      });
      return;
    }
    if (current.job?.needs_stage_reuse && current.job.stage) {
      await focusStageWorkbench({
        run: current,
        stageId: current.job.stage,
        selectStage,
        expandStage,
        setActiveStepId,
        setPipelineSubTab: setPipelineSubTabWrapped,
        substepId: `stage_reuse:${current.job.stage}`,
        blockingReason: "stage_reuse",
      });
      return;
    }
    const handoffStage = findHandoffStage(current);
    if (handoffStage) {
      await focusStageWorkbench({
        run: current,
        stageId: handoffStage.id,
        selectStage,
        expandStage,
        setActiveStepId,
        setPipelineSubTab: setPipelineSubTabWrapped,
        substepId: `handoff:${handoffStage.id}`,
        blockingReason: "handoff_review",
      });
      return;
    }
    if (hasActionRequiredStage(current.stages)) {
      const blocked = current.stages.find((s) => s.status === "action_required");
      if (blocked) {
        await focusStageWorkbench({
          run: current,
          stageId: blocked.id,
          selectStage,
          expandStage,
          setActiveStepId,
          setPipelineSubTab: setPipelineSubTabWrapped,
        });
      }
      return;
    }
    const next = findNextRunnableStage(current.stages, current.meta);
    if (!next) {
      showToast("No runnable stage — check gates or flow.");
      return;
    }
    if (
      next.id === "transcript_review" ||
      next.id === "g1_vo_pickup" ||
      next.id === "g2_flow_select"
    ) {
      await focusStageWorkbench({
        run: current,
        stageId: next.id,
        selectStage,
        expandStage,
        setActiveStepId,
        setPipelineSubTab: setPipelineSubTabWrapped,
      });
      return;
    }
    userDismissedActionRef.current = false;
    await focusStageWorkbench({
      run: current,
      stageId: next.id,
      selectStage,
      expandStage,
      setActiveStepId,
      setPipelineSubTab: setPipelineSubTabWrapped,
      substepId: "run",
    });
    showToast(readyForStageMessage(next.title), "info");
  }, [
    run,
    runId,
    showToast,
    selectStage,
    executeJob,
    beginStageExecution,
    openActionModal,
    refreshRun,
    setPipelineSubTabWrapped,
    expandStage,
    setActiveStepId,
  ]);

  const advanceFromCheckpoint = useCallback(async () => {
    userDismissedActionRef.current = false;
    setActionBusy(false);
    actionBusyRef.current = false;
    const completedStageId = selectedStageIdRef.current;
    await advancePipeline({
      run,
      runId,
      apiGrants: ALL_API_CONSENTS,
      selectedStageId: selectedStageIdRef.current,
      executeJob,
      selectStage,
      expandStage,
      setActiveSubstepId: setActiveSubstepIdState,
      setActiveStepId,
      setPipelineSubTab: setPipelineSubTabWrapped,
      showToast,
      refreshRun,
      navigateToNextBlocker: runNextStage,
      config,
      autoRun: true,
      acknowledgeHandoff: () => acknowledgeHandoffRef.current(),
    });
    const refreshed = runId ? await refreshRun() : null;
    await syncPipelineStageFocusRef.current(refreshed);
    if (
      completedStageId &&
      refreshed?.stages.find((s) => s.id === completedStageId)?.status === "done"
    ) {
      collapseStage(completedStageId);
    }
    if (!actionBusyRef.current) {
      setActionModalOpen(false);
      userDismissedActionRef.current = false;
      lastAutoOpenKeyRef.current = null;
    }
  }, [
    run,
    runId,
    executeJob,
    selectStage,
    expandStage,
    showToast,
    refreshRun,
    runNextStage,
    setPipelineSubTabWrapped,
    collapseStage,
    setActiveStepId,
    config,
  ]);

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
      userDismissedActionRef.current = false;
      await refreshRun();
      await pollLog(true);
      setActionModalOpen(false);
      setActionBusy(false);
      actionBusyRef.current = false;
      await advanceFromCheckpoint();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Handoff acknowledgment failed";
      appendClientLog(msg, "warning", stageId);
      showToast(msg, "error");
    }
  }, [
    selectedStageId,
    runId,
    run,
    showToast,
    refreshRun,
    logOperatorAction,
    appendClientLog,
    pollLog,
    advanceFromCheckpoint,
  ]);

  useEffect(() => {
    acknowledgeHandoffRef.current = acknowledgeHandoff;
  }, [acknowledgeHandoff]);

  const syncPipelineStageFocusCb = useCallback(
    async (runOverride?: RunData | null): Promise<boolean> => {
      if (jobRunningRef.current) return false;
      return syncPipelineStageFocus({
        run: runOverride ?? run,
        runId,
        apiGrants: ALL_API_CONSENTS,
        selectedStageId: selectedStageIdRef.current,
        executeJob,
        selectStage,
        expandStage,
        setActiveSubstepId: setActiveSubstepIdState,
        setActiveStepId,
        setPipelineSubTab: setPipelineSubTabWrapped,
        showToast,
        refreshRun,
        navigateToNextBlocker: runNextStage,
        config,
      });
    },
    [
      run,
      runId,
      config,
      executeJob,
      selectStage,
      expandStage,
      showToast,
      refreshRun,
      runNextStage,
      setPipelineSubTabWrapped,
      setActiveStepId,
    ],
  );

  useEffect(() => {
    syncPipelineStageFocusRef.current = syncPipelineStageFocusCb;
  }, [syncPipelineStageFocusCb]);

  const autoContinuePipeline = useCallback(
    async (completedStageId?: string | null): Promise<boolean> => {
      if (
        autopilotInFlightRef.current ||
        jobRunningRef.current ||
        actionBusyRef.current ||
        approveInFlightRef.current
      ) {
        return false;
      }
      if (
        shouldSkipDuplicateAutoContinue(
          completedStageId,
          autoContinueDedupeRef.current,
        )
      ) {
        return false;
      }
      if (config?.journey_ui?.enabled === false) return false;
      autoContinueDedupeRef.current = recordAutoContinue(completedStageId);
      autopilotInFlightRef.current = true;
      try {
        const opts: AdvancePipelineOpts = {
          run,
          runId,
          apiGrants: ALL_API_CONSENTS,
          selectedStageId: selectedStageIdRef.current,
          executeJob,
          selectStage,
          expandStage,
          setActiveSubstepId: setActiveSubstepIdState,
          setActiveStepId,
          setPipelineSubTab: setPipelineSubTabWrapped,
          showToast,
          refreshRun,
          navigateToNextBlocker: runNextStage,
          config,
          autoRun: true,
          acknowledgeHandoff: () => acknowledgeHandoffRef.current(),
        };
        return await tryAutoContinuePipeline({
          ...opts,
          completedStageId,
        });
      } finally {
        autopilotInFlightRef.current = false;
      }
    },
    [
      run,
      runId,
      config,
      executeJob,
      selectStage,
      expandStage,
      showToast,
      refreshRun,
      runNextStage,
      setPipelineSubTabWrapped,
      setActiveStepId,
    ],
  );

  useEffect(() => {
    autoContinuePipelineRef.current = autoContinuePipeline;
  }, [autoContinuePipeline]);

  const approveWriteAndContinue = useCallback(
    async (stageId?: string): Promise<boolean> => {
      if (!runId || !run) return false;
      if (approveInFlightRef.current) {
        return false;
      }
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
      const liveJob = await syncJobRunning(runId);
      if (isJobActivelyRunning(liveJob)) {
        const savingSameStage =
          liveJob?.mode === "write_approval" &&
          (liveJob.pending_write_stage === sid || liveJob.stage === sid);
        if (savingSameStage) {
          setActivityLogTabState("live");
          activityLogTabRef.current = "live";
          startJobPoll();
          return false;
        }
        const { jobRunning: busy } = await reconcileBusyRun({
          runId,
          syncJobRunning,
          refreshRun,
          startJobPoll,
          setActivityLogTab: setActivityLogTabState,
          showToast,
          context: "save",
        });
        if (busy) return false;
      }
      approveInFlightRef.current = true;
      setActionBusy(true);
      actionBusyRef.current = true;
      setJobRunning(true);
      setRun((prev) =>
        prev
          ? {
              ...prev,
              job: {
                ...prev.job,
                status: "running",
                mode: "write_approval",
                stage: sid,
                current_stage: sid,
                pending_write_stage: sid,
                pending_write_paths: paths,
                message: `Saving ${paths.length} file(s) for ${sid.replace(/_/g, " ")}…`,
              },
            }
          : prev,
      );
      setActivityLogTabState("live");
      activityLogTabRef.current = "live";
      startJobPoll();
      let keepBusyForJob = false;
      try {
        await runStepPrimaryPrep("write_approval");
        const res = await api<{
          ok?: boolean;
          flushed?: string[];
          stage_id?: string;
          started_stage?: string | null;
          job?: JobState;
        }>(`/api/runs/${runId}/continue-after-checkpoint`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: "write_approval", stage_id: sid }),
        });

        traceAction(
          "gui.write_approval.save",
          `Saving ${paths.length} staged file(s) for ${sid.replace(/_/g, " ")}…`,
          { level: "action", stage: sid },
        );

        const nextStageId = res.started_stage ?? null;
        const patched = patchRunAfterWriteApproval(run, {
          savedStageId: sid,
          nextStageId,
          job: res.job,
        });
        setRun(patched);
        setRunState(patched);
        bumpLocalVersion();
        userDismissedActionRef.current = false;
        lastAutoOpenKeyRef.current = null;
        setActionModalOpen(false);
        collapseStage(sid);
        setPipelineSubTabWrapped("stage");

        showToast(
          sid === "disfluency_extract"
            ? nextStageId === "disfluency_review"
              ? "Filler catalog saved — review clips to continue."
              : "Filler catalog saved — review complete, continuing pipeline."
            : "Outputs saved.",
        );
        traceAction(
          "gui.write_approval.saved",
          nextStageId
            ? `Files saved. Ready for ${nextStageId.replace(/_/g, " ")}.`
            : "Files saved — step complete.",
          { level: "success", stage: sid },
        );
        appendClientLog(
          sid === "disfluency_extract"
            ? nextStageId === "disfluency_review"
              ? `Saved ${paths.length} file(s) for disfluency extract — open Disfluency review next.`
              : `Saved ${paths.length} file(s) for disfluency extract — review already complete.`
            : nextStageId
              ? `Saved ${paths.length} file(s) for ${sid.replace(/_/g, " ")} — ready for ${nextStageId.replace(/_/g, " ")}.`
              : `Saved ${paths.length} file(s) for ${sid.replace(/_/g, " ")} — step complete.`,
          "success",
          sid,
          "gui.write_approval.saved",
        );

        if (nextStageId) {
          expandStage(nextStageId);
          const focusStepId =
            nextStageId === "disfluency_review" ? "review_fillers" : "run";
          await selectStage(nextStageId, { stepId: focusStepId });
          setActiveSubstepIdState(`run:${nextStageId}`);

          if (res.job?.ok === false) {
            if (res.job.needs_stage_reuse) {
              setActiveSubstepIdState(`stage_reuse:${nextStageId}`);
              showToast(
                "Files saved — choose reuse from a prior run or run ingest fresh.",
                "success",
              );
            }
            await refreshRun();
            await pollLog(true);
            return true;
          }

          if (
            isPipelineAutopilotEnabled(config) &&
            canAutoRunStage(nextStageId)
          ) {
            await executeJob(executeBodyForStage(nextStageId), {
              source: "checkpoint_continue",
            });
            await refreshRun();
            await pollLog(true);
            return true;
          }

          showToast(readyForStageMessage(nextStageId.replace(/_/g, " ")), "info");
          await refreshRun();
          await pollLog(true);
          return true;
        }

        const advanced = await advancePipeline({
          run: patched,
          runId,
          apiGrants: ALL_API_CONSENTS,
          selectedStageId: selectedStageIdRef.current,
          executeJob,
          selectStage,
          expandStage,
          setActiveSubstepId: setActiveSubstepIdState,
          setActiveStepId,
          setPipelineSubTab: setPipelineSubTabWrapped,
          showToast,
          refreshRun,
          navigateToNextBlocker: runNextStage,
          config,
          autoRun: true,
          acknowledgeHandoff: () => acknowledgeHandoffRef.current(),
        });
        await refreshRun();
        await pollLog(true);
        return advanced;
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Approve failed";
        appendClientLog(msg, "warning", sid, "gui.write_approval.error");
        showToast(msg, "error");
        if (e instanceof ApiError && e.status === 409 && runId) {
          const { jobRunning: busy, writeApprovalCleared } = await reconcileBusyRun({
            runId,
            syncJobRunning,
            refreshRun,
            startJobPoll,
            setActivityLogTab: setActivityLogTabState,
            showToast,
            context: "save",
          });
          if (busy) {
            keepBusyForJob = true;
            if (writeApprovalCleared) setActionModalOpen(false);
            return writeApprovalCleared;
          }
        }
        return false;
      } finally {
        if (!keepBusyForJob) {
          approveInFlightRef.current = false;
          setActionBusy(false);
          actionBusyRef.current = false;
        }
      }
    },
    [
      runId,
      run,
      showToast,
      appendClientLog,
      refreshRun,
      runNextStage,
      executeJob,
      logOperatorAction,
      traceAction,
      pollLog,
      syncJobRunning,
      startJobPoll,
      selectStage,
      expandStage,
      setPipelineSubTabWrapped,
      handleJobStartResponse,
      collapseStage,
      setActiveSubstepIdState,
      config,
    ],
  );

  const revalidateArtifactIssues = useCallback(
    async (stageId: string) => {
      if (!runId) return;
      try {
        const res = await api<{
          ok?: boolean;
          open_blocking?: number;
          errors?: string[];
          downstream_errors?: string[];
        }>(`/api/runs/${runId}/stages/${stageId}/issues/revalidate`, { method: "POST" });
        await refreshRun();
        const hasDownstream = (res.downstream_errors?.length ?? 0) > 0;
        if (res.ok && !res.open_blocking && !hasDownstream) {
          showToast("Validation passed — you can save staged files", "success");
          return;
        }
        showToast(
          res.downstream_errors?.[0] ||
            res.errors?.[0] ||
            `${res.open_blocking ?? 0} issue(s) remain`,
          "warning",
        );
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Re-check failed";
        showToast(msg, "error");
      }
    },
    [runId, refreshRun, showToast],
  );

  const fixAllAndContinueStage = useCallback(
    async (stageId: string): Promise<boolean> => {
      if (!runId) return false;
      setActionBusy(true);
      try {
        const res = await api<{
          outcome?: string;
          phase?: string;
          can_advance_pipeline?: boolean;
          downstream_job?: unknown;
          errors?: string[];
          open_blocking?: number;
        }>(`/api/runs/${runId}/stages/${stageId}/issues/auto-resolve`, { method: "POST" });
        await refreshRun();
        const outcome = res.outcome || "unknown";
        if (outcome === "success") {
          if (res.downstream_job) {
            showToast("Fixes applied — downstream re-run started", "success");
            startJobPoll();
            return true;
          }
          if (res.can_advance_pipeline && res.phase === "awaiting_save") {
            showToast("All issues resolved — saving staged files", "success");
            return await approveWriteAndContinue(stageId);
          }
          showToast("All issues resolved", "success");
          return true;
        }
        if (outcome === "manual_required" || outcome === "partial") {
          showToast(res.errors?.[0] || "Some issues need manual review", "warning");
          return false;
        }
        showToast(res.errors?.[0] || `Auto-resolve: ${outcome}`, "error");
        return false;
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Fix all failed";
        showToast(msg, "error");
        return false;
      } finally {
        setActionBusy(false);
      }
    },
    [runId, refreshRun, showToast, approveWriteAndContinue, startJobPoll],
  );

  const discardPendingWrites = useCallback(
    async (stageId: string) => {
      if (!runId) return;
      try {
        await api(`/api/runs/${runId}/pending-writes/${stageId}/discard`, {
          method: "POST",
        });
        showToast("Discarded staged outputs — re-run this step when ready.");
        appendClientLog(`Write approval discarded for ${stageId}`, "info");
        await refreshRun();
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Discard failed";
        showToast(msg, "error");
        appendClientLog(msg, "error", stageId);
      }
    },
    [runId, showToast, appendClientLog, refreshRun],
  );

  const completeTranscriptReview = useCallback(
    async (acceptUnreviewed = false) => {
      if (!runId) return;
      await runStepPrimaryPreps(["transcript_dock_flush", "transcript_review_flush"]);
      await api(`/api/runs/${runId}/transcript-review/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accept_unreviewed: acceptUnreviewed }),
      });
      showToast("Transcript review complete");
      await refreshRun();
      await advanceFromCheckpoint();
    },
    [runId, showToast, refreshRun, advanceFromCheckpoint],
  );

  const completeDisfluencyReview = useCallback(
    async (acceptUnreviewed = false) => {
      if (!runId) return;
      await api(`/api/runs/${runId}/disfluency-review/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accept_unreviewed: acceptUnreviewed }),
      });
      showToast("Disfluency review complete");
      await refreshRun();
      await advanceFromCheckpoint();
    },
    [runId, showToast, refreshRun, advanceFromCheckpoint],
  );

  const approveSfxPrompts = useCallback(
    async () => {
      if (!runId) return;
      await runStepPrimaryPrep("sfx_prompt_review");
      await api(`/api/runs/${runId}/sfx-prompts/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved_by: "operator_gui" }),
      });
      showToast("Prompts approved.");
      await refreshRun();
      if (selectedStageIdRef.current) {
        await selectStage(selectedStageIdRef.current);
      }
      await advanceFromCheckpoint();
    },
    [runId, showToast, refreshRun, selectStage, advanceFromCheckpoint],
  );

  const skipOptionalStage = useCallback(
    async (stageId: string) => {
      if (!runId || !run) return;
      const stage = run.stages.find((s) => s.id === stageId);
      if (!stage) return;

      const workbench = {
        selectStage,
        expandStage,
        setActiveStepId,
        setPipelineSubTab: setPipelineSubTabWrapped,
      };

      const reuseOutcome = await handleReuseFromAssetsForStage({
        runId,
        run,
        stage,
        refreshRun,
        showToast,
        autoContinuePipeline,
        ...workbench,
      });
      if (reuseOutcome === "reused" || reuseOutcome === "failed") return;

      const offer = resolvePrecleanOffer(stage, run.meta);
      if (!offer) {
        showToast(
          "No prior outputs are available for this step — use Run to execute it.",
          "info",
        );
        await focusStageWorkbench({
          run,
          stageId,
          ...workbench,
          substepId: "run",
        });
        return;
      }

      try {
        await api(`/api/runs/${runId}/preclean-offer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            checkpoint: offer.checkpoint,
            action: "dismiss",
            scope: offer.scope,
          }),
        });
        showToast("Skipped optional step — not required for this run.");
        const refreshed = await refreshRun();
        if (await autoContinuePipeline(stageId)) return;
        const next = await focusNextRunnableStageWorkbench(refreshed ?? run, workbench);
        if (next) showToast(readyForStageMessage(next.title), "info");
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Could not skip optional step";
        showToast(msg, "error");
        appendClientLog(msg, "warning", stageId);
      }
    },
    [
      runId,
      run,
      showToast,
      refreshRun,
      appendClientLog,
      selectStage,
      expandStage,
      setActiveStepId,
      setPipelineSubTabWrapped,
      autoContinuePipeline,
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
      userDismissedActionRef.current = false;
      await advanceFromCheckpoint();
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
    advanceFromCheckpoint,
    selectStage,
    setPipelineSubTabWrapped,
    expandStage,
    openActionModal,
  ]);

  const activateSubstep = useCallback(
    (substep: StageSubstep) => {
      if (guardBusy(jobRunningRef.current, actionBusyRef.current, showToast)) {
        return;
      }
      setActiveTabState("pipeline");
      const stepId = substepIdToStepId(substep.id);
      void selectStage(substep.stageId, { stepId });
      expandStage(substep.stageId);
      if (stepId) scrollToStageStep(stepId);
    },
    [selectStage, expandStage, showToast],
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
      showToast(msg, "error");
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
        showToast(msg, "error");
      }

      const runQuery = new URLSearchParams(window.location.search).get("run");
      const restoreRunId = runQuery || active?.run_id;

      if (!restoreRunId) {
        if (gen === bootGenRef.current) setSessionReady(true);
      }

      void (async () => {
        try {
          await refreshHome({ enrichRuns: true });
          if (gen !== bootGenRef.current) return;
          if (!restoreRunId) return;
          const stageId = active?.selected_stage_id ?? null;
          selectedStageIdRef.current = stageId;
          setSelectedStageId(stageId);
          if (active?.active_step_id) {
            activeStepIdRef.current = active.active_step_id;
            setActiveStepIdState(active.active_step_id);
          }
          const restoreTab = active?.active_tab ?? "pipeline";
          prefetchTab(restoreTab);
          await openRun(restoreRunId, {
            quiet: true,
            selectedStageId: stageId,
            activeTab: restoreTab,
            pipelineSubTab: active?.pipeline_sub_tab ?? "stage",
            force: Boolean(runQuery),
          });
          if (active?.activity_log_tab) {
            setActivityLogTabState(active.activity_log_tab as LogStreamTab);
            activityLogTabRef.current = active.activity_log_tab as LogStreamTab;
          }
          if (typeof active?.activity_log_collapsed === "boolean") {
            setActivityLogCollapsedState(active.activity_log_collapsed);
            activityLogCollapsedRef.current = active.activity_log_collapsed;
          }
          if (Array.isArray(active?.pipeline_collapsed_stages)) {
            setPipelineCollapsedStages(active.pipeline_collapsed_stages);
            pipelineCollapsedRef.current = active.pipeline_collapsed_stages;
          }
          if (Array.isArray(active?.pipeline_expanded_done_stages)) {
            setPipelineExpandedDoneStages(active.pipeline_expanded_done_stages);
            pipelineExpandedDoneRef.current = active.pipeline_expanded_done_stages;
          }
          if (typeof active?.pipeline_filter_needs_you === "boolean") {
            setPipelineFilterNeedsYouState(active.pipeline_filter_needs_you);
            pipelineFilterNeedsYouRef.current = active.pipeline_filter_needs_you;
          }
          if (gen !== bootGenRef.current) return;
          if (serverRestarted && runIdRef.current) {
            const rid = runIdRef.current;
            await syncJobRunning(rid);
            const runData = await api<RunData>(`/api/runs/${rid}`);
            setRun(runData);
            setRunState(runData);
            renderLogWithAlerts(runData.log_tail || []);
          }
        } catch {
          /* enrich/restore failures surface via toasts from openRun/refreshHome */
        } finally {
          if (gen === bootGenRef.current) setSessionReady(true);
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
    maybePingForRequiredAttention(
      run,
      alertsMuted,
      lastAttentionPingKeyRef,
      mergedApiGrants(),
    );
  }, [run, alertsMuted, mergedApiGrants]);

  useEffect(() => {
    if (!run) return;
    const focusId = findPendingFocusStage(run, mergedApiGrants());
    if (!focusId) return;
    expandStage(focusId);
  }, [
    run?.journey?.blocking,
    run?.job?.status,
    run?.job?.needs_stage_reuse,
    run?.job?.stage,
    expandStage,
    mergedApiGrants,
  ]);

  useEffect(() => {
    if (!run) return;
    const opAction = resolveOperatorAction(run, {
      selectedStageId: selectedStageIdRef.current,
      jobRunning: jobRunningRef.current,
      apiGrants: ALL_API_CONSENTS,
    });
    const substepId = run.journey?.active_substep_id ?? opAction.substepId;
    if (substepId) {
      setActiveSubstepIdState((prev) => (prev === substepId ? prev : substepId));
    }
    if (opAction.stageId) {
      setPipelineCollapsedStages((prev) => {
        if (!prev.includes(opAction.stageId!)) return prev;
        return prev.filter((id) => id !== opAction.stageId);
      });
    }
  }, [
    run?.journey?.blocking,
    run?.job?.status,
    run?.job?.needs_stage_reuse,
    run?.journey?.active_substep_id,
    run?.job?.stage,
  ]);

  useEffect(() => {
    if (activeTab === "executions") void refreshHome();
  }, [activeTab, refreshHome]);

  const isStagePinned = useMemo(() => {
    if (!pinnedStageId || !run || !selectedStageId || pinnedStageId !== selectedStageId) {
      return false;
    }
    const focusId = resolveOperatorAction(run, {
      selectedStageId,
      jobRunning,
      apiGrants: ALL_API_CONSENTS,
    }).stageId;
    return Boolean(focusId && selectedStageId !== focusId);
  }, [pinnedStageId, run, selectedStageId, jobRunning]);

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
    activeStepId,
    setActiveStepId,
    pipelineCollapsedStages,
    pipelineExpandedDoneStages,
    pipelineFilterNeedsYou,
    isStagePinned,
    setPipelineFilterNeedsYou,
    setActivityLogTab,
    setActivityLogCollapsed,
    setLogFilterPreset,
    pinSelectedStage,
    setActiveTab,
    setPipelineSubTab: setPipelineSubTabWrapped,
    navigatePipelineSubTab,
    openArtifactInEditor,
    setSelectedAsset,
    setMenuOpen,
    showToast,
    dismissToast,
    openActionModal,
    closeActionModal,
    closeActionModalAfterSuccess,
    clearSession,
    refreshHome,
    startRun,
    openRun,
    retryOpenRun,
    refreshRun,
    selectStage,
    executeJob,
    beginStageExecution,
    runNextStage,
    redoFromStage,
    startJobPoll,
    acknowledgeHandoff,
    approveWriteAndContinue,
    fixAllAndContinueStage,
    revalidateArtifactIssues,
    discardPendingWrites,
    completeTranscriptReview,
    completeDisfluencyReview,
    approveSfxPrompts,
    advanceFromCheckpoint,
    autoContinuePipeline,
    syncPipelineStageFocus: syncPipelineStageFocusCb,
    onCheckpointContinue,
    setCheckpointBusy,
    setAlertsMuted,
    appendClientLog,
    traceAction,
    dumpLastStep,
    loadTranscriptReview,
    setTranscriptReview,
    confirm,
    resolveConfirm,
    activateSubstep,
    setActiveSubstepId,
    skipOptionalStage,
    expandStage,
    collapseStage,
    toggleDoneStageExpanded,
  };

  return (
    <SessionProvider
      value={{
        sessionReady,
        sessionLoadError,
        serverActiveRunId,
        activeTab,
        pipelineSubTab,
        setActiveTab: setActiveTabState,
        setPipelineSubTab,
        clearSession,
        activityLogTab,
        activityLogCollapsed,
      }}
    >
      <RunProvider
        value={{
          runId,
          run,
          runs,
          selectedStageId,
          selectedStage,
          openRunLoading,
          openRun,
          refreshRun,
          selectStage,
          startRun,
          refreshHome,
        }}
      >
        <JobProvider
          value={{
            jobRunning,
            actionBusy,
            executeJob,
            startJobPoll,
            runNextStage,
            approveWriteAndContinue,
            advanceFromCheckpoint,
          }}
        >
          <AppContext.Provider value={value}>
            {children}
            <PrecleanOffersBridge
              shown={shownPrecleanOffers}
              setShown={setShownPrecleanOffers}
              runId={runId}
            />
          </AppContext.Provider>
        </JobProvider>
      </RunProvider>
    </SessionProvider>
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
