import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../context/AppContext";
import type {
  AssemblyTimelineData,
  NleState,
  TimelineMode,
  TimelineSegment,
  TranscriptState,
  TranscriptWord,
  VoLine,
  WaveformPeaksData,
} from "../types";

export type DirtyReason = "structural" | "trim" | null;

export function useTimelineEditor() {
  const { runId, timeline, refreshRun, run } = useApp();
  const [mode, setMode] = useState<TimelineMode>("source");
  const [zoom, setZoom] = useState(1);
  const [playheadMs, setPlayheadMs] = useState(0);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [assembly, setAssembly] = useState<AssemblyTimelineData | null>(null);
  const [transcript, setTranscript] = useState<TranscriptState | null>(null);
  const [words, setWords] = useState<TranscriptWord[]>([]);
  const [waveform, setWaveform] = useState<WaveformPeaksData | null>(null);
  const [selectionOrder, setSelectionOrder] = useState<string[]>([]);
  const [narrativePlan, setNarrativePlan] = useState<Record<string, unknown> | null>(null);
  const [dirtyReason, setDirtyReason] = useState<DirtyReason>(null);
  const [nleSnapshot, setNleSnapshot] = useState<NleState | null>(null);
  const [assemblyDurationBefore, setAssemblyDurationBefore] = useState<number | null>(null);
  const playerRef = useRef<HTMLAudioElement>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const nle = timeline?.nle || null;
  const segments = timeline?.segments || [];
  const voLines = timeline?.vo_lines || [];
  const durationMs = timeline?.duration_ms || 1;
  const assemblyDurationMs = assembly?.timeline_duration_ms || 0;

  useEffect(() => {
    if (nle?.zoom) setZoom(nle.zoom);
    if (nle?.playhead_ms != null) setPlayheadMs(nle.playhead_ms);
  }, [nle?.zoom, nle?.playhead_ms]);

  const loadTranscript = useCallback(async () => {
    if (!runId) return;
    try {
      const data = await api<TranscriptState>(`/api/runs/${runId}/transcript`);
      setTranscript(data);
      setWords(data.words || []);
    } catch {
      setTranscript(null);
      setWords([]);
    }
  }, [runId]);

  const loadAssembly = useCallback(async () => {
    if (!runId) return;
    try {
      const data = await api<AssemblyTimelineData>(`/api/runs/${runId}/assembly-timeline`);
      setAssembly(data);
    } catch {
      setAssembly({ ready: false, reason: "Failed to load assembly timeline." });
    }
  }, [runId]);

  const loadWaveform = useCallback(async () => {
    if (!runId || !timeline?.normalized_audio) return;
    try {
      const data = await api<WaveformPeaksData>(
        `/api/runs/${runId}/waveform?path=${encodeURIComponent(timeline.normalized_audio)}`,
      );
      setWaveform(data);
    } catch {
      setWaveform(null);
    }
  }, [runId, timeline?.normalized_audio]);

  const loadAuxiliary = useCallback(async () => {
    if (!runId) return;
    void loadTranscript();
    void loadAssembly();
    void loadWaveform();
    try {
      const sel = await api<{ ordered_segment_ids?: string[] }>(
        `/api/runs/${runId}/artifact?path=${encodeURIComponent("flow_1_master/selection.json")}`,
      );
      setSelectionOrder(sel.ordered_segment_ids || []);
    } catch {
      setSelectionOrder([]);
    }
    try {
      const plan = await api<Record<string, unknown>>(
        `/api/runs/${runId}/artifact?path=${encodeURIComponent("flow_1_master/narrative_plan.json")}`,
      );
      setNarrativePlan(plan);
    } catch {
      setNarrativePlan(null);
    }
  }, [runId, loadTranscript, loadAssembly, loadWaveform]);

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
      await api(`/api/runs/${runId}/nle`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data }),
      });
    },
    [runId, nle, playheadMs, zoom],
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

  const setPlayheadOnly = useCallback((ms: number) => {
    setPlayheadMs(ms);
  }, []);

  const seekTo = useCallback((ms: number) => {
    setPlayheadMs(ms);
    if (playerRef.current) playerRef.current.currentTime = ms / 1000;
    debouncedSavePrefs(undefined, ms);
  }, [debouncedSavePrefs]);

  const selectSegment = useCallback(
    (segId: string, startMs: number) => {
      setSelectedSegmentId(segId);
      seekTo(startMs);
    },
    [seekTo],
  );

  const snapshotNle = useCallback(() => {
    if (nle) setNleSnapshot(JSON.parse(JSON.stringify(nle)) as NleState);
  }, [nle]);

  const patchSegment = useCallback(
    async (segmentId: string, patch: Record<string, unknown>, reason?: DirtyReason) => {
      if (!runId) return;
      snapshotNle();
      await api(`/api/runs/${runId}/nle/segment`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segment_id: segmentId, patch }),
      });
      if (reason) setDirtyReason(reason);
      await refreshRun();
    },
    [runId, refreshRun, snapshotNle],
  );

  const patchSelectedSegment = useCallback(
    async (patch: Record<string, unknown>, reason: DirtyReason = "structural") => {
      if (!selectedSegmentId) return;
      await patchSegment(selectedSegmentId, patch, reason);
    },
    [selectedSegmentId, patchSegment],
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
    snapshotNle();
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
  }, [selectedSegmentId, runId, playheadMs, refreshRun, snapshotNle]);

  const reorderSegment = useCallback(
    async (dragId: string, targetId: string) => {
      if (!dragId || dragId === targetId || !runId) return;
      snapshotNle();
      const order = nle?.sequence_order?.length
        ? [...nle.sequence_order]
        : segments.map((s) => s.segment_id || s._nle_label || "");
      const from = order.indexOf(dragId);
      const to = order.indexOf(targetId);
      if (from < 0 || to < 0) return;
      order.splice(from, 1);
      order.splice(to, 0, dragId);
      await api(`/api/runs/${runId}/nle`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data: { ...(nle || {}), sequence_order: order, playhead_ms: playheadMs, zoom },
        }),
      });
      setDirtyReason("structural");
      await refreshRun();
    },
    [nle, segments, runId, playheadMs, zoom, refreshRun, snapshotNle],
  );

  const revertLastEdit = useCallback(async () => {
    if (!runId || !nleSnapshot) return;
    await api(`/api/runs/${runId}/nle`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data: nleSnapshot }),
    });
    setNleSnapshot(null);
    setDirtyReason(null);
    await refreshRun();
  }, [runId, nleSnapshot, refreshRun]);

  const selectedSegment = segments.find((s) => s.segment_id === selectedSegmentId) || null;

  const sourceAudioPath = timeline?.normalized_audio
    ? `/api/runs/${runId}/audio?path=${encodeURIComponent(timeline.normalized_audio)}`
    : `/api/runs/${runId}/source-audio`;

  const assemblyAudioPath =
    assembly?.preview_audio && runId
      ? `/api/runs/${runId}/audio?path=${encodeURIComponent(assembly.preview_audio)}`
      : undefined;

  const activeAudioPath = mode === "assembly" && assemblyAudioPath ? assemblyAudioPath : sourceAudioPath;

  const activeDurationMs = mode === "assembly" && assemblyDurationMs > 0 ? assemblyDurationMs : durationMs;

  return {
    run,
    runId,
    mode,
    setMode,
    zoom,
    setZoom: (z: number) => {
      setZoom(z);
      debouncedSavePrefs(z);
    },
    playheadMs,
    setPlayheadOnly,
    seekTo,
    selectedSegmentId,
    selectedSegment,
    selectSegment,
    segments,
    voLines,
    durationMs,
    nle,
    assembly,
    transcript,
    words,
    waveform,
    selectionOrder,
    narrativePlan,
    dirtyReason,
    setDirtyReason,
    playerRef,
    patchSegment,
    patchSelectedSegment,
    applyTrim,
    snapBoundary,
    splitAtPlayhead,
    reorderSegment,
    revertLastEdit,
    refreshRun,
    loadAssembly,
    loadAuxiliary,
    sourceAudioPath,
    assemblyAudioPath,
    activeAudioPath,
    activeDurationMs,
    assemblyDurationBefore,
    setAssemblyDurationBefore,
    nleSnapshot,
  };
}

export function segmentManifestBounds(seg: TimelineSegment): { start: number; end: number } {
  return {
    start: seg._manifest_start_ms ?? seg.start_ms,
    end: seg._manifest_end_ms ?? seg.end_ms,
  };
}

export function voLinesForSegment(voLines: VoLine[], segmentId: string): VoLine[] {
  return voLines.filter((v) => v.targets_segment_id === segmentId);
}
