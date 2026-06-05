import { useCallback, useEffect, useMemo } from "react";
import { api } from "../../../api/client";
import { useTimelineEditor } from "../../../hooks/useTimelineEditor";
import { formatMs } from "../../../utils";
import { ApplyEditsPanel } from "./ApplyEditsPanel";
import { AssemblyTimeline } from "./AssemblyTimeline";
import { SegmentInspector } from "./SegmentInspector";
import { SourceTimeline } from "./SourceTimeline";
import { TimelineQcBanner } from "./TimelineQcBanner";
import { TimelineToolbar } from "./TimelineToolbar";
import { TranscriptStrip } from "./TranscriptStrip";

export function TimelineWorkspace() {
  const editor = useTimelineEditor();
  const {
    run,
    runId,
    mode,
    setMode,
    zoom,
    setZoom,
    playheadMs,
    seekTo,
    setPlayheadOnly,
    selectedSegmentId,
    selectedSegment,
    selectSegment,
    segments,
    voLines,
    durationMs,
    nle,
    assembly,
    words,
    waveform,
    selectionOrder,
    narrativePlan,
    dirtyReason,
    setDirtyReason,
    playerRef,
    patchSelectedSegment,
    patchSegment,
    applyTrim,
    snapBoundary,
    splitAtPlayhead,
    reorderSegment,
    revertLastEdit,
    loadAssembly,
    activeAudioPath,
    activeDurationMs,
    assemblyDurationBefore,
    setAssemblyDurationBefore,
    nleSnapshot,
    refreshRun,
  } = editor;

  const widthPx = Math.max(800, activeDurationMs / 50) * zoom;

  const focusRange = useMemo(() => {
    if (!selectedSegment) return null;
    return {
      start_ms: selectedSegment.start_ms,
      end_ms: selectedSegment.end_ms,
      label: selectedSegment.segment_id,
    };
  }, [selectedSegment]);

  const chapters = useMemo(() => {
    const raw = (narrativePlan?.chapters as Array<Record<string, unknown>>) || [];
    return raw.map((ch) => ({
      title: String(ch.title || ch.chapter_title || ""),
      anchor_segment_id: String(ch.anchor_segment_id || ch.opens_with_segment_id || ""),
    }));
  }, [narrativePlan]);

  useEffect(() => {
    if (mode === "assembly") void loadAssembly();
  }, [mode, loadAssembly]);

  const handleTrim = useCallback(
    async (segId: string, startMs: number, endMs: number, snap: boolean) => {
      await applyTrim(segId, startMs, endMs, snap);
    },
    [applyTrim],
  );

  const handleSnapTrimSelected = useCallback(async () => {
    if (!selectedSegment?.segment_id) return;
    const sid = selectedSegment.segment_id;
    const start = await snapBoundary(sid, selectedSegment.start_ms, "start");
    const end = await snapBoundary(sid, selectedSegment.end_ms, "end");
    await applyTrim(sid, start, end, false);
  }, [selectedSegment, snapBoundary, applyTrim]);

  const handleTightenPauses = useCallback(async () => {
    if (!selectedSegment?.segment_id || !words.length) return;
    const sid = selectedSegment.segment_id;
    const segWords = words.filter(
      (w) => w.start_ms >= selectedSegment.start_ms && w.end_ms <= selectedSegment.end_ms,
    );
    if (!segWords.length) return;
    const last = segWords[segWords.length - 1];
    await applyTrim(sid, selectedSegment.start_ms, last.end_ms + 50, true);
  }, [selectedSegment, words, applyTrim]);

  const handleTrimAsides = useCallback(async () => {
    for (const seg of segments) {
      if (seg.type === "aside" && seg.segment_id && !seg._excluded) {
        await patchSegment(seg.segment_id, { excluded: true }, "structural");
      }
    }
  }, [segments, patchSegment]);

  const handleRippleDelete = useCallback(async () => {
    if (!selectedSegmentId || !runId || !nle) return;
    const order = nle.sequence_order?.length
      ? nle.sequence_order.filter((id) => id !== selectedSegmentId)
      : segments
          .map((s) => s.segment_id || "")
          .filter((id) => id && id !== selectedSegmentId);
    await api(`/api/runs/${runId}/nle`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        data: {
          ...nle,
          sequence_order: order,
          segment_overrides: {
            ...(nle.segment_overrides || {}),
            [selectedSegmentId]: {
              ...(nle.segment_overrides?.[selectedSegmentId] || {}),
              excluded: true,
            },
          },
        },
      }),
    });
    setDirtyReason("structural");
    await refreshRun();
  }, [selectedSegmentId, runId, nle, segments, setDirtyReason, refreshRun]);

  const handleAddMarker = useCallback(async () => {
    if (!runId || !nle) return;
    const markers = [...(nle.markers || [])];
    markers.push({
      at_ms: Math.round(playheadMs),
      label: selectedSegmentId || "marker",
      note: "operator",
    });
    await api(`/api/runs/${runId}/nle`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data: { ...nle, markers } }),
    });
    await refreshRun();
  }, [runId, nle, playheadMs, selectedSegmentId, refreshRun]);

  if (!segments.length) {
    return (
      <div className="panel nle-panel">
        <p className="empty-state">NLE timeline appears after segment classification.</p>
      </div>
    );
  }

  return (
    <div className="panel nle-panel timeline-workspace">
      <div className="panel-head">
        <h3>Non-linear editor</h3>
        <TimelineToolbar
          mode={mode}
          zoom={zoom}
          dirtyReason={dirtyReason}
          segments={segments}
          selectedSegmentId={selectedSegmentId}
          onModeChange={setMode}
          onZoomChange={setZoom}
          onSplit={() => void splitAtPlayhead()}
          onExclude={() => void patchSelectedSegment({ excluded: true }, "structural")}
          onMarkRedo={() => void patchSelectedSegment({ mark_redo: true }, "structural")}
          onTrimAsides={() => void handleTrimAsides()}
          onTightenPauses={() => void handleTightenPauses()}
          onRippleDelete={() => void handleRippleDelete()}
          onRestore={() => void patchSelectedSegment({ excluded: false, mark_redo: false }, "structural")}
          onSnapTrim={() => void handleSnapTrimSelected()}
          onAddMarker={() => void handleAddMarker()}
        />
      </div>

      <p className="muted">
        {segments.length} segments · {formatMs(mode === "assembly" ? activeDurationMs : durationMs)} ·
        zoom {zoom}x · {mode} view
      </p>

      <TimelineQcBanner
        run={run}
        nle={nle}
        segments={segments}
        voLines={voLines}
        narrativePlan={narrativePlan}
      />

      <ApplyEditsPanel
        nle={nle}
        runId={runId}
        assemblyDurationBefore={assemblyDurationBefore}
        assemblyDurationAfter={assembly?.timeline_duration_ms ?? null}
        previewAudioPath={
          assembly?.preview_audio && runId
            ? `/api/runs/${runId}/audio?path=${encodeURIComponent(assembly.preview_audio)}`
            : undefined
        }
        canRevert={!!nleSnapshot}
        onRevert={() => void revertLastEdit()}
        onBeforeApply={(d) => setAssemblyDurationBefore(d)}
        onApplied={() => void loadAssembly()}
      />

      <div className="timeline-main-layout">
        <div className="timeline-canvas">
          {mode === "source" ? (
            <SourceTimeline
              segments={segments}
              voLines={voLines}
              durationMs={durationMs}
              widthPx={widthPx}
              zoom={zoom}
              playheadMs={playheadMs}
              selectedSegmentId={selectedSegmentId}
              waveform={waveform}
              chapters={chapters}
              markers={nle?.markers}
              onSeek={seekTo}
              onSelect={selectSegment}
              onReorder={(a, b) => void reorderSegment(a, b)}
              onTrim={(id, s, e, snap) => void handleTrim(id, s, e, snap)}
            />
          ) : assembly?.ready ? (
            <AssemblyTimeline
              assembly={assembly}
              widthPx={widthPx}
              playheadMs={playheadMs}
              selectedSegmentId={selectedSegmentId}
              onSeek={seekTo}
              onSelectSpeech={(segId, ms) => selectSegment(segId, ms)}
            />
          ) : (
            <p className="empty-state">{assembly?.reason || "Assembly timeline not ready — apply edits or run edl_flow1."}</p>
          )}
        </div>

        <SegmentInspector
          segment={selectedSegment}
          voLines={voLines}
          selectionOrder={selectionOrder}
          playheadMs={playheadMs}
          onPatch={(p) => void patchSelectedSegment(p, "structural")}
          onTrim={(s, e, snap) => {
            if (selectedSegment?.segment_id) void handleTrim(selectedSegment.segment_id, s, e, snap);
          }}
          onSplit={() => void splitAtPlayhead()}
          onSnapTrim={() => void handleSnapTrimSelected()}
        />
      </div>

      <TranscriptStrip
        words={words}
        playheadMs={playheadMs}
        focusRange={focusRange}
        onSeek={seekTo}
        onWordRangeSelect={(start, end) => {
          if (selectedSegment?.segment_id) void handleTrim(selectedSegment.segment_id, start, end, true);
        }}
      />

      <audio
        ref={playerRef}
        controls
        className="audio-player"
        key={activeAudioPath}
        src={activeAudioPath}
        onTimeUpdate={() => {
          if (playerRef.current) setPlayheadOnly(playerRef.current.currentTime * 1000);
        }}
      />
    </div>
  );
}
