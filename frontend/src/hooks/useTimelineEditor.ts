import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { formatApiError, isExpectedEmptyApiError } from "../utils/safeApi";
import { api } from "../api/client";
import { useApp } from "../context/AppContext";
import { useNleHistory } from "./useNleHistory";
import type {
  AssemblyTimelineData,
  NleState,
  TimelineMode,
  TranscriptState,
  TranscriptWord,
  VoLine,
  WaveformPeaksData,
} from "../types";
import {
  DEFAULT_TIMELINE_FILTERS,
  expandToSentenceEndMs,
  filterSegments,
  lowConfidenceSpans,
  parseSegmentIdFromQcMessage,
  reviewQueueForFilter,
  segmentIdForTime,
  silenceTrimBounds,
  tightenEndMs,
  type ReviewFilter,
  type TimelineFilters,
} from "../utils/nleHelpers";
import { togglePlayPause } from "../utils/audioPlayback";

export type DirtyReason = "structural" | "trim" | null;

export function useTimelineEditor() {
  const { runId, timeline, refreshRun, run, showToast, appendClientLog } = useApp();
  const [mode, setMode] = useState<TimelineMode>("source");
  const [zoom, setZoomState] = useState(1);
  const [playheadMs, setPlayheadMs] = useState(0);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [selectedSegmentIds, setSelectedSegmentIds] = useState<string[]>([]);
  const [assembly, setAssembly] = useState<AssemblyTimelineData | null>(null);
  const [transcript, setTranscript] = useState<TranscriptState | null>(null);
  const [words, setWords] = useState<TranscriptWord[]>([]);
  const [waveform, setWaveform] = useState<WaveformPeaksData | null>(null);
  const [selectionOrder, setSelectionOrder] = useState<string[]>([]);
  const [narrativePlan, setNarrativePlan] = useState<Record<string, unknown> | null>(null);
  const [contentBrief, setContentBrief] = useState<Record<string, unknown> | null>(null);
  const [dirtyReason, setDirtyReason] = useState<DirtyReason>(null);
  const [assemblyDurationBefore, setAssemblyDurationBefore] = useState<number | null>(null);
  const [snapEnabled, setSnapEnabled] = useState(true);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [loopSelection, setLoopSelection] = useState(false);
  const [followPlayback, setFollowPlayback] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [filters, setFilters] = useState<TimelineFilters>(DEFAULT_TIMELINE_FILTERS);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("all");
  const [reviewIndex, setReviewIndex] = useState(0);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [scrollLeftPx, setScrollLeftPx] = useState(0);
  const [priorPreviewUrl, setPriorPreviewUrl] = useState<string | null>(null);
  const playerRef = useRef<HTMLAudioElement>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timelineScrollRef = useRef<HTMLDivElement>(null);
  const history = useNleHistory();

  const nle = timeline?.nle || null;
  const segments = timeline?.segments || [];
  const voLines = timeline?.vo_lines || [];
  const durationMs = timeline?.duration_ms || 1;
  const lowThreshold = transcript?.low_confidence_threshold ?? 0.85;

  useEffect(() => {
    if (nle?.zoom) setZoomState(nle.zoom);
    if (nle?.playhead_ms != null) setPlayheadMs(nle.playhead_ms);
  }, [nle?.zoom, nle?.playhead_ms]);

  useEffect(() => {
    if (playerRef.current) playerRef.current.playbackRate = playbackSpeed;
  }, [playbackSpeed]);

  const loadTranscript = useCallback(async () => {
    if (!runId) return;
    try {
      const data = await api<TranscriptState>(`/api/runs/${runId}/transcript`);
      setTranscript(data);
      setWords(data.words || []);
    } catch (reason) {
      setTranscript(null);
      setWords([]);
      if (!isExpectedEmptyApiError(reason)) {
        appendClientLog(formatApiError(reason, "Transcript"), "error");
      }
    }
  }, [runId, appendClientLog]);

  const loadAssembly = useCallback(async () => {
    if (!runId) return;
    try {
      const data = await api<AssemblyTimelineData>(`/api/runs/${runId}/assembly-timeline`);
      setAssembly(data);
    } catch (reason) {
      setAssembly({ ready: false, reason: formatApiError(reason, "Assembly timeline") });
      if (!isExpectedEmptyApiError(reason)) {
        appendClientLog(formatApiError(reason, "Assembly timeline"), "error");
      }
    }
  }, [runId, appendClientLog]);

  const loadWaveform = useCallback(async () => {
    if (!runId || !timeline?.normalized_audio) return;
    try {
      const data = await api<WaveformPeaksData>(
        `/api/runs/${runId}/waveform?path=${encodeURIComponent(timeline.normalized_audio)}`,
      );
      setWaveform(data);
    } catch (reason) {
      setWaveform(null);
      if (!isExpectedEmptyApiError(reason)) {
        appendClientLog(formatApiError(reason, "Waveform"), "error");
      }
    }
  }, [runId, timeline?.normalized_audio, appendClientLog]);

  const loadAuxiliary = useCallback(async () => {
    if (!runId) return;
    void loadTranscript();
    void loadAssembly();
    void loadWaveform();
    try {
      const sel = await api<{ ordered_segment_ids?: string[] }>(
        `/api/runs/${runId}/artifact?path=${encodeURIComponent("master/selection.json")}`,
      );
      setSelectionOrder(sel.ordered_segment_ids || []);
    } catch (reason) {
      setSelectionOrder([]);
      if (!(reason instanceof ApiError && reason.status === 404)) {
        appendClientLog(formatApiError(reason, "Selection manifest"), "error");
      }
    }
    try {
      const plan = await api<Record<string, unknown>>(
        `/api/runs/${runId}/artifact?path=${encodeURIComponent("master/narrative_plan.json")}`,
      );
      setNarrativePlan(plan);
    } catch (reason) {
      setNarrativePlan(null);
      if (!(reason instanceof ApiError && reason.status === 404)) {
        appendClientLog(formatApiError(reason, "Narrative plan"), "error");
      }
    }
    try {
      const brief = await api<Record<string, unknown>>(
        `/api/runs/${runId}/artifact?path=${encodeURIComponent("understanding/content_brief.json")}`,
      );
      setContentBrief(brief);
    } catch (reason) {
      setContentBrief(null);
      if (!(reason instanceof ApiError && reason.status === 404)) {
        appendClientLog(formatApiError(reason, "Content brief"), "error");
      }
    }
  }, [runId, loadTranscript, loadAssembly, loadWaveform, appendClientLog]);

  useEffect(() => {
    void loadAuxiliary();
  }, [loadAuxiliary]);

  const saveNlePrefs = useCallback(
    async (nextZoom?: number, nextPlayhead?: number) => {
      if (!runId) return;
      const data = {
        ...(nle || {}),
        playhead_ms: Math.round(nextPlayhead ?? playheadMs),
        zoom: nextZoom ?? zoom,
      };
      try {
        await api(`/api/runs/${runId}/nle`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ data }),
        });
      } catch (reason) {
        appendClientLog(formatApiError(reason, "Save NLE prefs"), "error");
      }
    },
    [runId, nle, playheadMs, zoom, appendClientLog],
  );

  const debouncedSavePrefs = useCallback(
    (nextZoom?: number, nextPlayhead?: number) => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        void saveNlePrefs(nextZoom, nextPlayhead);
      }, 600);
    },
    [saveNlePrefs],
  );

  const restoreNleState = useCallback(
    async (state: NleState) => {
      if (!runId) return;
      try {
        await api(`/api/runs/${runId}/nle`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ data: state }),
        });
        setDirtyReason(null);
        await refreshRun();
      } catch (e) {
        showToast(e instanceof Error ? e.message : "Failed to restore NLE state");
      }
    },
    [runId, refreshRun, showToast],
  );

  const pushHistoryBefore = useCallback(
    (label?: string) => {
      if (nle) history.push(nle, label);
    },
    [nle, history],
  );

  useEffect(() => {
    if (nle && history.entries.length === 0) {
      history.push(nle, "Initial state");
    }
  }, [nle, history]);

  const setPlayheadOnly = useCallback((ms: number) => {
    setPlayheadMs(ms);
  }, []);

  const seekTo = useCallback(
    (ms: number) => {
      setPlayheadMs(ms);
      if (playerRef.current) playerRef.current.currentTime = ms / 1000;
      debouncedSavePrefs(undefined, ms);
    },
    [debouncedSavePrefs],
  );

  const selectSegment = useCallback(
    (segId: string, startMs: number, opts?: { additive?: boolean; range?: boolean }) => {
      if (opts?.additive) {
        setSelectedSegmentIds((prev) =>
          prev.includes(segId) ? prev.filter((id) => id !== segId) : [...prev, segId],
        );
        setSelectedSegmentId(segId);
      } else if (opts?.range && selectedSegmentId) {
        const ids = segments.map((s) => s.segment_id || "").filter(Boolean);
        const a = ids.indexOf(selectedSegmentId);
        const b = ids.indexOf(segId);
        if (a >= 0 && b >= 0) {
          const [lo, hi] = a < b ? [a, b] : [b, a];
          setSelectedSegmentIds(ids.slice(lo, hi + 1));
        } else {
          setSelectedSegmentIds([segId]);
        }
        setSelectedSegmentId(segId);
      } else {
        setSelectedSegmentId(segId);
        setSelectedSegmentIds([segId]);
      }
      seekTo(startMs);
    },
    [seekTo, selectedSegmentId, segments],
  );

  const patchSegment = useCallback(
    async (segmentId: string, patch: Record<string, unknown>, reason?: DirtyReason) => {
      if (!runId) return;
      pushHistoryBefore();
      try {
        await api(`/api/runs/${runId}/nle/segment`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ segment_id: segmentId, patch }),
        });
        if (reason) setDirtyReason(reason);
        await refreshRun();
      } catch (e) {
        showToast(e instanceof Error ? e.message : "Segment update failed");
      }
    },
    [runId, refreshRun, pushHistoryBefore, nle, history, showToast],
  );

  const patchSegments = useCallback(
    async (ids: string[], patch: Record<string, unknown>, reason: DirtyReason = "structural") => {
      if (!runId || !ids.length) return;
      pushHistoryBefore();
      showToast(`Updating ${ids.length} segment(s)…`, "info");
      try {
        await api(`/api/runs/${runId}/nle/batch`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operations: ids.map((segment_id) => ({ segment_id, patch })) }),
        });
        setDirtyReason(reason);
        await refreshRun();
        showToast("Timeline updated", "success");
      } catch (reason) {
        showToast(formatApiError(reason, "Batch segment update"), "error");
        appendClientLog(formatApiError(reason, "Batch segment update"), "error");
      }
    },
    [runId, refreshRun, pushHistoryBefore, showToast, appendClientLog],
  );

  const patchSelectedSegment = useCallback(
    async (patch: Record<string, unknown>, reason: DirtyReason = "structural") => {
      const ids = selectedSegmentIds.length ? selectedSegmentIds : selectedSegmentId ? [selectedSegmentId] : [];
      if (!ids.length) return;
      if (ids.length === 1) await patchSegment(ids[0], patch, reason);
      else await patchSegments(ids, patch, reason);
    },
    [selectedSegmentId, selectedSegmentIds, patchSegment, patchSegments],
  );

  const putNle = useCallback(
    async (data: NleState, reason?: DirtyReason, label?: string) => {
      if (!runId) return;
      pushHistoryBefore();
      try {
        await api(`/api/runs/${runId}/nle`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ data }),
        });
        if (reason) setDirtyReason(reason);
        await refreshRun();
        history.push(data, label);
      } catch (e) {
        const msg =
          e && typeof e === "object" && "message" in e
            ? String((e as { message: string }).message)
            : "NLE save failed";
        showToast(msg);
      }
    },
    [runId, refreshRun, pushHistoryBefore, nle, history, showToast],
  );

  const snapBoundary = useCallback(
    async (segmentId: string, ms: number, edge: "start" | "end") => {
      if (!runId) return ms;
      const res = await api<{ snapped_ms: number }>(`/api/runs/${runId}/nle/snap-boundary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segment_id: segmentId, ms: Math.round(ms), edge }),
      });
      return res.snapped_ms;
    },
    [runId],
  );

  const applyTrim = useCallback(
    async (segmentId: string, startMs: number, endMs: number, snap = false) => {
      const seg = segments.find((s) => s.segment_id === segmentId);
      if (!seg) return;
      let start = startMs;
      let end = endMs;
      if (snap) {
        start = await snapBoundary(segmentId, start, "start");
        end = await snapBoundary(segmentId, end, "end");
      }
      await patchSegment(segmentId, { start_ms: Math.round(start), end_ms: Math.round(end) }, "trim");
    },
    [segments, snapBoundary, patchSegment],
  );

  const splitAtPlayhead = useCallback(async () => {
    if (!selectedSegmentId || !runId) return;
    pushHistoryBefore();
    try {
      await api(`/api/runs/${runId}/nle/split`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segment_id: selectedSegmentId,
          at_ms: Math.round(playheadMs),
        }),
      });
      setDirtyReason("structural");
      await refreshRun();
    } catch (reason) {
      showToast(formatApiError(reason, "Split segment"), "error");
      appendClientLog(formatApiError(reason, "Split segment"), "error");
    }
  }, [selectedSegmentId, runId, playheadMs, refreshRun, pushHistoryBefore, showToast, appendClientLog]);

  const reorderSegment = useCallback(
    async (dragId: string, targetId: string) => {
      if (!dragId || dragId === targetId || !runId) return;
      pushHistoryBefore();
      const order = nle?.sequence_order?.length
        ? [...nle.sequence_order]
        : segments.map((s) => s.segment_id || s._nle_label || "");
      const from = order.indexOf(dragId);
      const to = order.indexOf(targetId);
      if (from < 0 || to < 0) return;
      order.splice(from, 1);
      order.splice(to, 0, dragId);
      await putNle(
        { ...(nle || {}), sequence_order: order, playhead_ms: playheadMs, zoom },
        "structural",
        "Reordered segments",
      );
    },
    [nle, segments, runId, playheadMs, zoom, putNle, pushHistoryBefore],
  );

  const undo = useCallback(async () => {
    const state = history.undoState();
    if (state) await restoreNleState(state);
  }, [history, restoreNleState]);

  const redo = useCallback(async () => {
    const state = history.redoState();
    if (state) await restoreNleState(state);
  }, [history, restoreNleState]);

  const restoreHistoryAt = useCallback(
    async (index: number) => {
      const state = history.restoreTo(index);
      if (state) await restoreNleState(state);
    },
    [history, restoreNleState],
  );

  const togglePlay = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    void togglePlayPause(player).catch(() => {
      showToast("Could not play timeline audio — check source or assembly preview.", "error");
    });
  }, [showToast]);

  const lowConfSpans = useMemo(
    () => lowConfidenceSpans(words, lowThreshold),
    [words, lowThreshold],
  );

  const lowConfSegmentIds = useMemo(() => {
    const ids = new Set<string>();
    for (const span of lowConfSpans) {
      const id = segmentIdForTime(segments, span.start_ms);
      if (id) ids.add(id);
    }
    return ids;
  }, [lowConfSpans, segments]);

  const qcSegmentIds = useMemo(() => {
    const ids = new Set<string>();
    const qc = run?.meta?.qc_summaries || {};
    for (const key of Object.keys(qc)) {
      const block = qc[key as keyof typeof qc] as { errors?: string[] } | undefined;
      for (const err of block?.errors || []) {
        const sid = parseSegmentIdFromQcMessage(err);
        if (sid) ids.add(sid);
      }
    }
    return ids;
  }, [run?.meta?.qc_summaries]);

  const filteredSegments = useMemo(
    () =>
      filterSegments(segments, filters, {
        selectionOrder,
        voLines,
        lowConfSegmentIds,
        qcSegmentIds,
      }),
    [segments, filters, selectionOrder, voLines, lowConfSegmentIds, qcSegmentIds],
  );

  const visibleSegmentIds = useMemo(
    () => new Set(filteredSegments.map((s) => s.segment_id || "")),
    [filteredSegments],
  );

  const reviewQueue = useMemo(
    () =>
      reviewQueueForFilter(reviewFilter, segments, {
        selectionOrder,
        lowConfSegmentIds,
        qcSegmentIds,
      }),
    [reviewFilter, segments, selectionOrder, lowConfSegmentIds, qcSegmentIds],
  );

  const reviewSegment = reviewQueue[reviewIndex] ?? null;

  const goReviewNext = useCallback(() => {
    setReviewIndex((i) => Math.min(i + 1, Math.max(0, reviewQueue.length - 1)));
  }, [reviewQueue.length]);

  const goReviewPrev = useCallback(() => {
    setReviewIndex((i) => Math.max(0, i - 1));
  }, []);

  const openReview = useCallback((filter: ReviewFilter) => {
    setReviewFilter(filter);
    setReviewIndex(0);
    setReviewOpen(true);
  }, []);

  useEffect(() => {
    if (!reviewOpen || !reviewSegment?.segment_id) return;
    selectSegment(reviewSegment.segment_id, reviewSegment.start_ms);
  }, [reviewOpen, reviewIndex, reviewSegment?.segment_id, reviewSegment?.start_ms, selectSegment]);

  const batchTightenPauses = useCallback(
    async (ids: string[]) => {
      for (const id of ids) {
        const seg = segments.find((s) => s.segment_id === id);
        if (!seg) continue;
        const end = tightenEndMs(seg, words);
        if (end != null) await applyTrim(id, seg.start_ms, end, true);
      }
    },
    [segments, words, applyTrim],
  );

  const batchSilenceTrim = useCallback(
    async (ids: string[]) => {
      for (const id of ids) {
        const seg = segments.find((s) => s.segment_id === id);
        if (!seg) continue;
        const bounds = silenceTrimBounds(seg, waveform, words);
        if (bounds) await applyTrim(id, bounds.start, bounds.end, snapEnabled);
      }
    },
    [segments, waveform, words, applyTrim, snapEnabled],
  );

  const selectedSegment = segments.find((s) => s.segment_id === selectedSegmentId) || null;

  const expandSelectedToSentence = useCallback(async () => {
    if (!selectedSegment?.segment_id) return;
    const end = expandToSentenceEndMs(selectedSegment, words);
    await applyTrim(selectedSegment.segment_id, selectedSegment.start_ms, end, true);
  }, [selectedSegment, words, applyTrim]);

  const assemblyDurationMsResolved = assembly?.timeline_duration_ms || 0;
  const activeDurationMs =
    mode === "assembly" && assemblyDurationMsResolved > 0
      ? assemblyDurationMsResolved
      : durationMs;

  const fitSelectionZoom = useCallback(() => {
    if (!selectedSegment) return;
    const dur = selectedSegment.end_ms - selectedSegment.start_ms;
    if (dur <= 0) return;
    const targetWidth = 480;
    const base = Math.max(800, activeDurationMs / 50);
    const newZoom = Math.min(8, Math.max(1, (targetWidth / dur) * (50 / base) * 3));
    setZoomState(newZoom);
    debouncedSavePrefs(newZoom);
    const scrollEl = timelineScrollRef.current;
    if (scrollEl) {
      const widthPx = base * newZoom;
      const left = (selectedSegment.start_ms / durationMs) * widthPx;
      scrollEl.scrollLeft = Math.max(0, left - 40);
      setScrollLeftPx(scrollEl.scrollLeft);
    }
  }, [selectedSegment, durationMs, activeDurationMs, debouncedSavePrefs]);

  const sourceAudioPath = timeline?.normalized_audio
    ? `/api/runs/${runId}/audio?path=${encodeURIComponent(timeline.normalized_audio)}`
    : `/api/runs/${runId}/source-audio`;

  const assemblyAudioPath =
    assembly?.preview_audio && runId
      ? `/api/runs/${runId}/audio?path=${encodeURIComponent(assembly.preview_audio)}`
      : undefined;

  const activeAudioPath = mode === "assembly" && assemblyAudioPath ? assemblyAudioPath : sourceAudioPath;

  const chapterAnchors = useMemo(() => {
    const raw = (narrativePlan?.chapters as Array<Record<string, unknown>>) || [];
    return raw.map((ch) => String(ch.anchor_segment_id || ch.opens_with_segment_id || "")).filter(Boolean);
  }, [narrativePlan]);

  const setZoom = useCallback(
    (z: number) => {
      setZoomState(z);
      debouncedSavePrefs(z);
    },
    [debouncedSavePrefs],
  );

  return {
    run,
    runId,
    mode,
    setMode,
    zoom,
    setZoom,
    playheadMs,
    setPlayheadOnly,
    seekTo,
    selectedSegmentId,
    selectedSegmentIds,
    selectedSegment,
    selectSegment,
    segments,
    filteredSegments,
    visibleSegmentIds,
    voLines,
    durationMs,
    nle,
    assembly,
    transcript,
    words,
    waveform,
    selectionOrder,
    narrativePlan,
    contentBrief,
    dirtyReason,
    setDirtyReason,
    playerRef,
    timelineScrollRef,
    patchSegment,
    patchSegments,
    patchSelectedSegment,
    applyTrim,
    snapBoundary,
    splitAtPlayhead,
    reorderSegment,
    undo,
    redo,
    restoreHistoryAt,
    history,
    refreshRun,
    loadAssembly,
    loadAuxiliary,
    sourceAudioPath,
    assemblyAudioPath,
    activeAudioPath,
    activeDurationMs,
    assemblyDurationBefore,
    setAssemblyDurationBefore,
    priorPreviewUrl,
    setPriorPreviewUrl,
    snapEnabled,
    setSnapEnabled,
    playbackSpeed,
    setPlaybackSpeed,
    loopSelection,
    setLoopSelection,
    followPlayback,
    setFollowPlayback,
    playing,
    setPlaying,
    togglePlay,
    filters,
    setFilters,
    reviewOpen,
    setReviewOpen,
    reviewFilter,
    setReviewFilter,
    reviewQueue,
    reviewIndex,
    setReviewIndex,
    reviewSegment,
    goReviewNext,
    goReviewPrev,
    openReview,
    batchTightenPauses,
    batchSilenceTrim,
    expandSelectedToSentence,
    fitSelectionZoom,
    scrollLeftPx,
    setScrollLeftPx,
    lowThreshold,
    lowConfSpans,
    lowConfSegmentIds,
    qcSegmentIds,
    chapterAnchors,
    putNle,
    showToast,
  };
}

export { segmentManifestBounds } from "../utils/nleHelpers";

export function voLinesForSegment(voLines: VoLine[], segmentId: string): VoLine[] {
  return voLines.filter((v) => v.targets_segment_id === segmentId);
}
