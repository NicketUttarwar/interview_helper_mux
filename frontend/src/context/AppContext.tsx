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
  HomunculusBrainInfo,
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
} from "../types";
import { formatApiError } from "../utils/safeApi";
import { isJobActivelyRunning } from "../utils/jobStatus";
import { isOperatorGateStartResponse } from "../utils/jobStartResponse";
import { countRequiredAttention } from "../utils/attentionQueue";
import { maybePingForRequiredAttention } from "../utils/attentionPing";
import { resolveOperatorAction } from "../utils/resolveOperatorAction";
import {
  actionSummaryText,
  resolveOperatorFocusStageId,
} from "../utils/checkpoint";
import { ALL_API_CONSENTS, mapGateToStage } from "../utils";
import type { ApiProvider } from "../types";
import {
  findActiveStage,
  findNextRunnableStage,
  hasActionRequiredStage,
  resolvePrecleanOffer,
} from "../utils/preclean";
import { firstUpstreamBlocker } from "../utils/stageOutputs";
import { runStepPrimaryPrep, runStepPrimaryPreps } from "../utils/stepPrimaryPrep";
import { describeExecuteBody } from "../utils/operatorActionLog";
import { guardBusy } from "../utils/guardBusy";
import { jobCompletionHint } from "../utils/jobCompletionHints";
import { scrollToStageStep } from "../utils/activateStageStep";
import { resolveVirtualPipelineFocus } from "../utils/virtualPipelineFocus";
import {
  advancePipeline,
  focusStageWorkbench,
  reconcileBusyRun,
  syncPipelineStageFocus,
  tryAutoContinuePipeline,
  type AdvancePipelineOpts,
  type ExecuteJobSource,
} from "../utils/checkpointContinuation";
import { isPipelineAutopilotEnabled } from "../utils/pipelineAutopilot";
import { resolveAutopilotCheckpoint } from "../utils/autopilotResolution";
import {
  focusNextRunnableStageWorkbench,
  handleReuseFromAssetsForStage,
  readyForStageMessage,
} from "../utils/stageAdvance";
import { recordAutoContinue, shouldSkipDuplicateAutoContinue } from "../utils/autoContinueDedupe";
import {
  resetAutoNavLedgerIfServerChanged,
  stageHadAutoNavigation,
} from "../utils/autoNavigationLedger";
import { shouldSuppressJobPollTerminalToast } from "../utils/jobPollToasts";
import { substepIdToStepId } from "../utils/resolveActiveStep";
import {
  shouldOpenTranscriptReuseEdit,
  syncTranscriptReuseEditConsumed,
} from "../utils/transcriptReuseEditGate";
import { clampPipelineSubTab } from "../utils/pipelineSubTabAvailability";
import { navigatePipelineSubTab as navigatePipelineSubTabUtil } from "../utils/navigatePipelineSubTab";
import { setRunState } from "./runStateStore";
import { JobProvider } from "./providers/JobProvider";
import { RunProvider } from "./providers/RunProvider";
import { SessionProvider } from "./providers/SessionProvider";
import type { StageSubstep } from "../types";
import { prefetchTab } from "../components/tabs/lazyTabs";
import {
  broadcastSessionTakeover,
  getClientInstanceId,
  parseSessionLeader,
  subscribeSessionBroadcast,
} from "../utils/sessionTabLeader";

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
  apiProviders: ApiProvider[];
  grantApiConsent: (provider: string, granted?: boolean) => Promise<void>;
  refreshApiGrants: () => Promise<void>;
  alertsMuted: boolean;
  jobRunning: boolean;
  actionBusy: boolean;
  transcriptReview: TranscriptReviewState | null;
  selectedStage: StageInfo | undefined;
  actionModalOpen: boolean;
  pendingActionCount: number;
  actionSummary: string | null;
  confirmMessage: string | null;
  transcriptReuseEditOpen: boolean;
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
  /** @deprecated Steps panel is always fully expanded — kept for session-payload compat. */
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
  openActionModal: () => void;
  closeActionModal: () => void;
  closeActionModalAfterSuccess: () => void;
  openTranscriptReuseEdit: () => void;
  closeTranscriptReuseEdit: () => void;
  clearSession: () => Promise<void>;
  refreshHome: (opts?: { enrichRuns?: boolean }) => Promise<void>;
  startRun: (inputPath: string) => Promise<void>;
  startRunMode: "manual" | "full-auto";
  setStartRunMode: (mode: "manual" | "full-auto") => void;
  homunculusVersion: string;
  setHomunculusVersion: (version: string) => void;
  homunculusBrains: HomunculusBrainInfo[];
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
  completeTranscriptReview: (acceptUnreviewed?: boolean) => Promise<void>;
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
  /** @deprecated no-op — done stages are never collapsed. */
  expandStage: (stageId: string) => void;
  /** @deprecated no-op — kept so existing callers don't need to change. */
  setPipelineFilterNeedsYou: (enabled: boolean) => void;
  sessionStale: boolean;
  takeOverSession: () => Promise<void>;
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
  const [startRunMode, setStartRunMode] = useState<"manual" | "full-auto">("manual");
  const [homunculusVersion, setHomunculusVersion] = useState("0.0.0");
  const [homunculusBrains, setHomunculusBrains] = useState<HomunculusBrainInfo[]>([
    {
      id: "0.0.0",
      label: "Original",
      summary:
        "Progress through the steps iteratively as they were created and originally intended.",
      kind: "original_pipeline",
    },
    {
      id: "0.1.0",
      label: "Homunculus",
      summary: "First homunculus brain: higher-level syncing, tool-loop conductor.",
      kind: "homunculus",
    },
  ]);
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [homeLog, setHomeLog] = useState<LogEntry[]>([]);
  const [assets, setAssets] = useState<AssetFile[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [alertsMuted, setAlertsMutedState] = useState(
    () => localStorage.getItem("gui_mute_alerts") === "1",
  );
  const [jobRunning, setJobRunning] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const appendClientLogRef = useRef<
    (message: string, level?: string, stage?: string, actionId?: string) => void
  >(() => {});
  const jobRunningRef = useRef(false);
  const actionBusyRef = useRef(false);
  const autopilotInFlightRef = useRef(false);
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
  const [transcriptReuseEditOpen, setTranscriptReuseEditOpen] = useState(false);

  useEffect(() => {
    setTranscriptReuseEditOpen(false);
  }, [runId]);
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
  // Steps panel always shows the full numbered list now (Refinement Pass cleanup) —
  // this stays permanently false and is kept only for session-payload compat.
  const [pipelineFilterNeedsYou] = useState(false);
  const [pinnedStageId, setPinnedStageId] = useState<string | null>(null);
  const [apiGrants, setApiGrants] = useState<Record<string, boolean>>(() => ({
    ...ALL_API_CONSENTS,
  }));
  const [apiProviders, setApiProviders] = useState<ApiProvider[]>([]);

  const recentClientLogRef = useRef<{ key: string; at: number } | null>(null);
  const logCountRef = useRef(0);
  const bootGenRef = useRef(0);
  const persistUiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runIdRef = useRef<string | null>(null);
  const selectedStageIdRef = useRef<string | null>(null);
  const activeTabRef = useRef<AppTab>("start");
  const activeStepIdRef = useRef<string | null>(null);
  const pipelineSubTabRef = useRef<PipelineSubTab>("stage");
  const activityLogTabRef = useRef<LogStreamTab>("all");
  const activityLogCollapsedRef = useRef(false);
  const lastAttentionPingKeyRef = useRef("");
  const confirmResolveRef = useRef<((ok: boolean) => void) | null>(null);
  const jobPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [sessionStale, setSessionStale] = useState(false);
  const sessionUiRevisionRef = useRef(0);
  const userDismissedActionRef = useRef(false);
  const lastAutoOpenKeyRef = useRef<string | null>(null);
  const userPinnedStageIdRef = useRef<string | null>(null);
  const runRefreshTickRef = useRef(0);

  const selectedStage = useMemo(
    () => run?.stages.find((s) => s.id === selectedStageId),
    [run, selectedStageId],
  );

  /** Operator-visible notices — written to gui_log.jsonl via appendClientLog, not overlay toasts. */
  const showToast = useCallback((msg: string, level: ToastLevel = "info") => {
    appendClientLogRef.current(
      msg,
      level,
      selectedStageIdRef.current || undefined,
      "gui.notice",
    );
  }, []);

  const refreshApiGrants = useCallback(async () => {
    try {
      const data = await api<{ providers: ApiProvider[]; grants: Record<string, boolean> }>(
        "/api/session/api-consent",
      );
      setApiProviders(data.providers || []);
      setApiGrants({ ...ALL_API_CONSENTS, ...(data.grants || {}) });
    } catch {
      setApiGrants({ ...ALL_API_CONSENTS });
    }
  }, []);

  const grantApiConsent = useCallback(
    async (provider: string, granted = true) => {
      const data = await api<{ grants: Record<string, boolean> }>("/api/session/api-consent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, granted }),
      });
      setApiGrants(data.grants || {});
      showToast(granted ? `${provider} API access granted.` : `${provider} access revoked.`);
    },
    [showToast],
  );

  const mergedApiGrants = useCallback(
    () => ({ ...ALL_API_CONSENTS, ...apiGrants }),
    [apiGrants],
  );

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
  const setActiveSubstepId = useCallback((id: string | null) => {
    setActiveSubstepIdState(id);
  }, []);

  // Steps panel never collapses stages anymore — kept as a stable no-op so the
  // many existing call sites (auto-navigation, checkpoints, etc.) don't need to change.
  const expandStage = useCallback((_stageId: string) => {}, []);

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
          // Steps panel is always fully visible now — send false unconditionally.
          pipeline_filter_needs_you: false,
          client_instance_id: getClientInstanceId(),
        }),
      })
        .then((active) => {
          const leader = parseSessionLeader(active as SessionActive);
          setSessionStale(!leader.isLeader);
          sessionUiRevisionRef.current = leader.uiRevision;
        })
        .catch((err) => {
          if (err instanceof ApiError && err.sessionSuperseded) {
            setSessionStale(true);
          }
        });
    }, 200);
  }, []);

  // No-op: the Steps panel no longer has a "needs you only" filter.
  const setPipelineFilterNeedsYou = useCallback((_enabled: boolean) => {}, []);

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
      setSelectedAsset(path);
      setPipelineSubTabWrapped("stage");
    },
    [setPipelineSubTabWrapped],
  );

  const closeActionModal = useCallback(() => {
    /* checkpoint modals removed — workbench is inline */
  }, []);

  const closeActionModalAfterSuccess = useCallback(() => {
    /* no-op */
  }, []);

  const openTranscriptReuseEdit = useCallback(() => {
    const rid = runIdRef.current;
    if (!shouldOpenTranscriptReuseEdit(rid, run?.meta)) return;
    setTranscriptReuseEditOpen(true);
  }, [run?.meta]);

  const closeTranscriptReuseEdit = useCallback(() => {
    setTranscriptReuseEditOpen(false);
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
        api<{ default?: string; brains?: HomunculusBrainInfo[] }>("/api/homunculus/versions"),
        (data) => {
          if (data.brains?.length) setHomunculusBrains(data.brains);
        },
        "Brains",
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
      const entry: LogEntry = {
        ts: new Date().toISOString(),
        level: level as LogEntry["level"],
        message,
        stage,
        detail: actionId ? { action_id: actionId, origin: "gui" } : undefined,
      };
      setLogEntries((prev) => [...prev, entry]);
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
  appendClientLogRef.current = appendClientLog;

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
      syncTranscriptReuseEditConsumed(runId, runData.meta);
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
      const virtual = resolveVirtualPipelineFocus(stageId);
      if (virtual) {
        setActiveTabState("pipeline");
        activeTabRef.current = "pipeline";
        setPipelineSubTabWrapped(virtual.subTab);
        persistSessionUi();
        return;
      }
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
        resolveOperatorFocusStageId(run, apiGrants) ?? "",
        run.stages.map((s) => `${s.id}:${s.status}`).join("|"),
        run.handoff_ack ? Object.keys(run.handoff_ack).sort().join(",") : "",
      ].join(":")
    : "";

  const navigateToOperatorFocus = useCallback(
    async (runOverride?: RunData | null) => {
      if (sessionStale) return false;
      const currentRun = runOverride ?? run;
      if (!currentRun) return false;
      const focusId = resolveOperatorFocusStageId(currentRun, mergedApiGrants());
      if (!focusId) return false;
      if (activeTabRef.current !== "pipeline") {
        setActiveTabState("pipeline");
        activeTabRef.current = "pipeline";
        persistSessionUi();
      }
      return syncPipelineStageFocusRef.current(runOverride ?? undefined);
    },
    [run, sessionStale, persistSessionUi],
  );

  useEffect(() => {
    if (!run || jobRunning) return;
    if (sessionStale) return;
    if (autopilotInFlightRef.current || actionBusyRef.current) {
      return;
    }
    const focusId = resolveOperatorFocusStageId(run, mergedApiGrants());
    const currentId = selectedStageIdRef.current;
    if (!focusId || focusId === currentId) return;
    // Already guided this source stage once this run.sh session — never yank back.
    if (stageHadAutoNavigation(focusId)) return;
    void navigateToOperatorFocus();
  }, [pipelineFocusKey, jobRunning, run, sessionStale, navigateToOperatorFocus]);

  useEffect(() => {
    if (!run || activeTabRef.current !== "pipeline" || jobRunning) return;
    if (autopilotInFlightRef.current || actionBusyRef.current) {
      return;
    }
    if (!isPipelineAutopilotEnabled(config)) return;
    const checkpoint = resolveAutopilotCheckpoint(run, config);
    if (!checkpoint) return;
    void autoContinuePipelineRef.current(checkpoint.stageId);
  }, [pipelineFocusKey, jobRunning, config]);

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
              } else if (polled.status === "stalled") {
                showToast(
                  polled.message || "Stage stalled — no progress recently. Safe to re-run.",
                  "warning",
                );
              } else if (
                polled.status === "gate" ||
                polled.status === "needs_operator"
              ) {
                if (
                  isPipelineAutopilotEnabled(config) &&
                  (polled.can_fix_all || polled.bridge_eligible)
                ) {
                  void autoContinuePipelineRef.current(polled.stage ?? null);
                } else {
                  showToast(
                    "Paused for your review — opening the checkpoint.",
                    "info",
                  );
                  userDismissedActionRef.current = false;
                  lastAutoOpenKeyRef.current = null;
                  void navigateToOperatorFocus(refreshed ?? undefined);
                }
              } else if (polled.status === "needs_clarification") {
                void autoContinuePipelineRef.current(polled.stage ?? null);
              } else if (
                polled.status !== "gate" &&
                polled.status !== "needs_operator"
              ) {
                const focusId = refreshed
                  ? resolveOperatorAction(refreshed, {
                      selectedStageId: selectedStageIdRef.current,
                      jobRunning: false,
                      apiGrants: mergedApiGrants(),
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
    config,
    selectStage,
    expandStage,
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
        showToast("Another action is in progress — watch Activity (Live).", "warning");
        return false;
      }
      const { stageId, kind, body } = opts;
      if (run?.stages?.length) {
        const upstream = firstUpstreamBlocker(run.stages, stageId, run.meta);
        if (upstream) {
          showToast(
            `Complete ${upstream.title} before running ${stageId.replace(/_/g, " ")}.`,
            "warning",
          );
          await selectStage(upstream.id);
          return false;
        }
      }
      const blocking = run?.journey?.blocking ?? run?.blocking;
      if (blocking?.blocked && blocking.stage_id && blocking.stage_id !== stageId) {
        showToast(blocking.message || "Complete the blocking stage first.", "warning");
        await selectStage(blocking.stage_id);
        return false;
      }
      const job = run?.job;
      if (
        job &&
        (job.status === "gate" || job.status === "needs_clarification") &&
        job.stage &&
        job.stage !== stageId
      ) {
        showToast("Finish the open gate before starting another stage.", "warning");
        await selectStage(job.stage);
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
                  api_consents: mergedApiGrants(),
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
                  api_consents: mergedApiGrants(),
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
        logOperatorAction(describeExecuteBody(body));
        markJobStarting(body.mode);
        try {
          const res = await api(`/api/runs/${runId}/execute`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...body, api_consents: mergedApiGrants() }),
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
        syncTranscriptReuseEditConsumed(id, runData.meta);
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
        const resolvedStage = opts.preferFirstStage
          ? findNextRunnableStage(runData.stages, runData.meta)?.id ??
            runData.stages[0]?.id ??
            null
          : stageId ||
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
        try {
          const claimed = await api<SessionActive>("/api/session/client", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              client_instance_id: getClientInstanceId(),
              force_takeover: Boolean(opts.force),
            }),
          });
          const leader = parseSessionLeader(claimed);
          setSessionStale(!leader.isLeader);
          sessionUiRevisionRef.current = leader.uiRevision;
        } catch {
          /* session leader optional during boot */
        }
        // One-time redirect to the stage that needs input (skipped if already guided).
        void navigateToOperatorFocus(runData);
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
    async (inputPath: string) => {
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
        const body: Record<string, unknown> = {
          input_audio_path: inputPath,
          run_mode: startRunMode,
          full_auto: startRunMode === "full-auto",
          homunculus_version: homunculusVersion,
        };
        showToast(
          startRunMode === "full-auto"
            ? "Creating execution and launching Full-auto…"
            : "Creating execution…",
          "info",
        );
        const res = await api<{ run_id: string; run_mode?: string }>(
          "/api/runs",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
        );
        appendClientLog(
          startRunMode === "full-auto"
            ? `Created execution ${res.run_id} (Full-auto)`
            : `Created execution ${res.run_id}`,
          "success",
        );
        if (startRunMode === "full-auto") {
          showToast(
            "Full-auto running — gates, package, and S3 publish are automatic.",
            "info",
          );
        }
        await openRun(res.run_id, { preferFirstStage: true });
      } catch (e) {
        showToast(e instanceof Error ? e.message : "Failed to start run", "error");
      }
    },
    [appendClientLog, openRun, showToast, runId, sessionReady, startRunMode, homunculusVersion],
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
    const blocking = current.journey?.blocking ?? current.blocking;
    if (blocking?.blocked && blocking.stage_id) {
      const sid = blocking.stage_id;
      const substepId =
        blocking.reason === "stage_reuse"
          ? `stage_reuse:${sid}`
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
      next.id === "g1_vo_pickup"
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
    await advancePipeline({
      run,
      runId,
      apiGrants: mergedApiGrants(),
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
      navigationIntent: "user_continue",
    });
    const refreshed = runId ? await refreshRun() : null;
    await syncPipelineStageFocusRef.current(refreshed);
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
    setActiveStepId,
    config,
  ]);

  const syncPipelineStageFocusCb = useCallback(
    async (runOverride?: RunData | null): Promise<boolean> => {
      if (jobRunningRef.current) return false;
      return syncPipelineStageFocus({
        run: runOverride ?? run,
        runId,
        apiGrants: mergedApiGrants(),
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
        actionBusyRef.current
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
          apiGrants: mergedApiGrants(),
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
    if (selectedStage.id === "g1_vo_pickup" && current.g1_clear) {
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
    refreshRun,
    advanceFromCheckpoint,
    setPipelineSubTabWrapped,
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
      appendClientLog(msg, "warning");
    }
  }, [selectedStageId, runId, refreshRun, confirm, appendClientLog]);

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
        await refreshApiGrants();
        const session = await api<{
          server?: { started_at?: string };
          active?: SessionActive | null;
          log?: LogEntry[];
        }>("/api/session");
        if (gen !== bootGenRef.current) return;
        const startedAt = session.server?.started_at;
        const prevStarted = localStorage.getItem(GUI_SERVER_STARTED_AT_KEY);
        serverRestarted = Boolean(startedAt && prevStarted && startedAt !== prevStarted);
        if (startedAt) {
          resetAutoNavLedgerIfServerChanged(startedAt);
          localStorage.setItem(GUI_SERVER_STARTED_AT_KEY, startedAt);
        }
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
          if (gen !== bootGenRef.current) return;
          if (!restoreRunId) return;
          const stageId = serverRestarted ? null : (active?.selected_stage_id ?? null);
          const virtualRestore = stageId ? resolveVirtualPipelineFocus(stageId) : null;
          const restoreStageId = virtualRestore ? null : stageId;
          selectedStageIdRef.current = restoreStageId;
          setSelectedStageId(restoreStageId);
          if (!serverRestarted && active?.active_step_id) {
            activeStepIdRef.current = active.active_step_id;
            setActiveStepIdState(active.active_step_id);
          } else if (serverRestarted) {
            activeStepIdRef.current = null;
            setActiveStepIdState(null);
          }
          const restoreTab = serverRestarted ? "pipeline" : (active?.active_tab ?? "pipeline");
          prefetchTab(restoreTab);
          await openRun(restoreRunId, {
            quiet: true,
            selectedStageId: restoreStageId,
            preferFirstStage: serverRestarted,
            activeTab: restoreTab,
            pipelineSubTab: virtualRestore
              ? virtualRestore.subTab
              : serverRestarted
                ? "stage"
                : (active?.pipeline_sub_tab ?? "stage"),
            force: Boolean(runQuery) || serverRestarted,
          });
          if (active?.activity_log_tab) {
            setActivityLogTabState(active.activity_log_tab as LogStreamTab);
            activityLogTabRef.current = active.activity_log_tab as LogStreamTab;
          }
          if (typeof active?.activity_log_collapsed === "boolean") {
            setActivityLogCollapsedState(active.activity_log_collapsed);
            activityLogCollapsedRef.current = active.activity_log_collapsed;
          }
          // pipeline_collapsed_stages / pipeline_expanded_done_stages / pipeline_filter_needs_you
          // are no longer read — the Steps panel is always fully visible and expanded.
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
          if (gen === bootGenRef.current) {
            setSessionReady(true);
            // Enriched runs list only feeds the Executions tab. Awaiting it here stalls
            // the active-run restore for as long as /api/runs?enrich takes, which grows
            // with the number of executions on disk.
            void refreshHome({ enrichRuns: true });
          }
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
    const focusId = resolveOperatorFocusStageId(run, mergedApiGrants());
    if (!focusId) return;
    expandStage(focusId);
    if (!sessionStale && focusId !== selectedStageIdRef.current) {
      void navigateToOperatorFocus();
    }
  }, [
    run?.journey?.blocking,
    run?.job?.status,
    run?.job?.needs_stage_reuse,
    run?.job?.stage,
    expandStage,
    mergedApiGrants,
    navigateToOperatorFocus,
    sessionStale,
  ]);

  const takeOverSession = useCallback(async () => {
    try {
      const claimed = await api<SessionActive>("/api/session/client", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_instance_id: getClientInstanceId(),
          force_takeover: true,
        }),
      });
      const leader = parseSessionLeader(claimed);
      setSessionStale(!leader.isLeader);
      sessionUiRevisionRef.current = leader.uiRevision;
      broadcastSessionTakeover(leader.clientInstanceId, leader.uiRevision);
      await refreshRun();
      await navigateToOperatorFocus();
      showToast("This tab is now controlling the session.", "success");
    } catch (e) {
      showToast(formatApiError(e, "Could not take over session"), "error");
    }
  }, [refreshRun, navigateToOperatorFocus, showToast]);

  useEffect(() => {
    const syncLeader = () => {
      if (!runIdRef.current) return;
      void api<{ active?: SessionActive }>("/api/session")
        .then((payload) => {
          const leader = parseSessionLeader(payload.active);
          setSessionStale(!leader.isLeader);
          if (leader.uiRevision > sessionUiRevisionRef.current) {
            sessionUiRevisionRef.current = leader.uiRevision;
            void refreshRun().then((refreshed) => {
              if (refreshed && leader.isLeader) void navigateToOperatorFocus(refreshed);
            });
          }
        })
        .catch(() => {});
    };
    const onVis = () => {
      if (document.visibilityState === "visible") syncLeader();
    };
    document.addEventListener("visibilitychange", onVis);
    const unsub = subscribeSessionBroadcast((msg) => {
      if (msg.type === "takeover") syncLeader();
    });
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      unsub();
    };
  }, [refreshRun, navigateToOperatorFocus]);

  useEffect(() => {
    if (!run) return;
    const opAction = resolveOperatorAction(run, {
      selectedStageId: selectedStageIdRef.current,
      jobRunning: jobRunningRef.current,
      apiGrants: mergedApiGrants(),
    });
    const substepId = run.journey?.active_substep_id ?? opAction.substepId;
    if (substepId) {
      setActiveSubstepIdState((prev) => (prev === substepId ? prev : substepId));
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
      apiGrants: mergedApiGrants(),
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
    apiGrants: mergedApiGrants(),
    apiProviders,
    grantApiConsent,
    refreshApiGrants,
    alertsMuted,
    jobRunning,
    actionBusy,
    transcriptReview,
    selectedStage,
    actionModalOpen,
    pendingActionCount,
    actionSummary,
    confirmMessage,
    transcriptReuseEditOpen,
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
    pipelineFilterNeedsYou,
    isStagePinned,
    setPipelineFilterNeedsYou,
    sessionStale,
    takeOverSession,
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
    openActionModal,
    closeActionModal,
    closeActionModalAfterSuccess,
    openTranscriptReuseEdit,
    closeTranscriptReuseEdit,
    clearSession,
    refreshHome,
    startRun,
    startRunMode,
    setStartRunMode,
    homunculusVersion,
    setHomunculusVersion,
    homunculusBrains,
    openRun,
    retryOpenRun,
    refreshRun,
    selectStage,
    executeJob,
    beginStageExecution,
    runNextStage,
    redoFromStage,
    startJobPoll,
    completeTranscriptReview,
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
