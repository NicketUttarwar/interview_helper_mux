import { useCallback, useEffect, useMemo, useState } from "react";
import { useApp } from "../../../context/AppContext";
import { useTimelineEditor } from "../../../hooks/useTimelineEditor";
import { formatMs } from "../../../utils";
import { parseSegmentIdFromQcMessage } from "../../../utils/nleHelpers";
import { ApplyEditsPanel } from "./ApplyEditsPanel";
import { AssemblyTimeline } from "./AssemblyTimeline";
import { EditHistoryPanel } from "./EditHistoryPanel";
import { ReviewQueuePanel } from "./ReviewQueuePanel";
import { SegmentInspector } from "./SegmentInspector";
import { SmartActionsPanel } from "./SmartActionsPanel";
import { SourceTimeline } from "./SourceTimeline";
import { TimelineFilterBar } from "./TimelineFilterBar";
import { TimelineMiniMap } from "./TimelineMiniMap";
import { TimelineQcChecklist } from "./TimelineQcChecklist";
import { TimelineToolbar } from "./TimelineToolbar";
import { TimelineTransport } from "./TimelineTransport";
import { TranscriptStrip } from "./TranscriptStrip";

export function TimelineWorkspace() {
  const { setPipelineSubTab } = useApp();
  const [hintDismissed, setHintDismissed] = useState(
    () => sessionStorage.getItem("timeline_desktop_hint_dismissed") === "1",
  );
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
    words,
    waveform,
    selectionOrder,
    narrativePlan,
    contentBrief,
    dirtyReason,
    playerRef,
    timelineScrollRef,
    patchSelectedSegment,
    patchSegment,
    patchSegments,
    applyTrim,
    snapBoundary,
    splitAtPlayhead,
    reorderSegment,
    undo,
    redo,
    restoreHistoryAt,
    history,
    loadAssembly,
    activeAudioPath,
    activeDurationMs,
    assemblyDurationBefore,
    setAssemblyDurationBefore,
    priorPreviewUrl,
    setPriorPreviewUrl,
    refreshRun,
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
    chapterAnchors,
    putNle,
  } = editor;

  const widthPx = Math.max(800, activeDurationMs / 50) * zoom;
  const viewportWidthPx = 800;

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

  const segmentQcIssues = useMemo(() => {
    if (!selectedSegmentId) return [];
    const qc = run?.meta?.qc_summaries || {};
    const issues: string[] = [];
    for (const block of Object.values(qc)) {
      const errors = (block as { errors?: string[] })?.errors || [];
      for (const err of errors) {
        if (parseSegmentIdFromQcMessage(err) === selectedSegmentId) issues.push(err);
      }
    }
    return issues;
  }, [run?.meta?.qc_summaries, selectedSegmentId]);

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
    const ids = selectedSegmentIds.length ? selectedSegmentIds : [selectedSegment.segment_id];
    await batchTightenPauses(ids);
  }, [selectedSegment, selectedSegmentIds, words, batchTightenPauses]);

  const handleTrimAsides = useCallback(async () => {
    const ids = segments
      .filter((s) => s.type === "aside" && !s._excluded)
      .map((s) => s.segment_id!)
      .filter(Boolean);
    await patchSegments(ids, { excluded: true }, "structural");
  }, [segments, patchSegments]);

  const handleRippleDelete = useCallback(async () => {
    if (!selectedSegmentId || !runId || !nle) return;
    const order = nle.sequence_order?.length
      ? nle.sequence_order.filter((id) => id !== selectedSegmentId)
      : segments
          .map((s) => s.segment_id || "")
          .filter((id) => id && id !== selectedSegmentId);
    await putNle(
      {
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
      "structural",
      "Ripple delete",
    );
  }, [selectedSegmentId, runId, nle, segments, putNle]);

  const handleAddMarker = useCallback(async () => {
    if (!runId || !nle) return;
    const markers = [...(nle.markers || [])];
    markers.push({
      at_ms: Math.round(playheadMs),
      label: selectedSegmentId || "marker",
      note: "operator",
    });
    await putNle({ ...nle, markers }, undefined, "Added marker");
    await refreshRun();
  }, [runId, nle, playheadMs, selectedSegmentId, putNle, refreshRun]);

  const handleContextAction = useCallback(
    async (segId: string, actionId: string) => {
      const seg = segments.find((s) => s.segment_id === segId);
      if (!seg) return;
      switch (actionId) {
        case "exclude":
          await patchSegment(segId, { excluded: true }, "structural");
          break;
        case "restore":
          await patchSegment(segId, { excluded: false, mark_redo: false }, "structural");
          break;
        case "mark_redo":
          await patchSegment(segId, { mark_redo: true }, "structural");
          break;
        case "snap_trim": {
          const start = await snapBoundary(segId, seg.start_ms, "start");
          const end = await snapBoundary(segId, seg.end_ms, "end");
          await applyTrim(segId, start, end, false);
          break;
        }
        case "tighten":
          await batchTightenPauses([segId]);
          break;
        case "split":
          await splitAtPlayhead();
          break;
        case "silence_trim":
          await batchSilenceTrim([segId]);
          break;
      }
    },
    [segments, patchSegment, snapBoundary, applyTrim, batchTightenPauses, splitAtPlayhead, batchSilenceTrim],
  );

  const minimapSpans = useMemo(
    () =>
      segments.map((s) => ({
        id: s.segment_id || "",
        start: s.start_ms,
        end: s.end_ms,
        excluded: s._excluded,
      })),
    [segments],
  );

  if (!segments.length) {
    return (
      <div className="panel nle-panel">
        <p className="empty-state">NLE timeline appears after segment classification.</p>
      </div>
    );
  }

  return (
    <div className="panel nle-panel timeline-workspace">
      {!hintDismissed ? (
        <div className="timeline-desktop-hint banner panel-inset">
          <p className="hint">
            Timeline editing is desktop-oriented — use a wide screen, mouse for trim handles, and
            toolbar shortcuts.
          </p>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => {
              sessionStorage.setItem("timeline_desktop_hint_dismissed", "1");
              setHintDismissed(true);
            }}
          >
            Dismiss
          </button>
        </div>
      ) : null}
      <div className="panel-head">
        <h3>Non-linear editor</h3>
        <TimelineToolbar
          mode={mode}
          zoom={zoom}
          dirtyReason={dirtyReason}
          segments={segments}
          selectedSegmentId={selectedSegmentId}
          snapEnabled={snapEnabled}
          canUndo={history.canUndo}
          canRedo={history.canRedo}
          onModeChange={setMode}
          onZoomChange={setZoom}
          onSnapChange={setSnapEnabled}
          onFitSelection={() => void fitSelectionZoom()}
          onSplit={() => void splitAtPlayhead()}
          onExclude={() => void patchSelectedSegment({ excluded: true }, "structural")}
          onMarkRedo={() => void patchSelectedSegment({ mark_redo: true }, "structural")}
          onTrimAsides={() => void handleTrimAsides()}
          onTightenPauses={() => void handleTightenPauses()}
          onRippleDelete={() => void handleRippleDelete()}
          onRestore={() => void patchSelectedSegment({ excluded: false, mark_redo: false }, "structural")}
          onSnapTrim={() => void handleSnapTrimSelected()}
          onAddMarker={() => void handleAddMarker()}
          onOpenReview={() => openReview("all")}
          onUndo={() => void undo()}
          onRedo={() => void redo()}
        />
      </div>

      <p className="muted">
        {segments.length} segments · {formatMs(mode === "assembly" ? activeDurationMs : durationMs)} ·
        zoom {zoom}x · {mode} view
      </p>

      <SmartActionsPanel
        segments={segments}
        selectionOrder={selectionOrder}
        lowConfSegmentIds={editor.lowConfSegmentIds}
        selectedSegmentIds={selectedSegmentIds}
        onExcludeAsides={() => void handleTrimAsides()}
        onTightenAll={(ids) => void batchTightenPauses(ids)}
        onExcludeOffSelection={(ids) => void patchSegments(ids, { excluded: true }, "structural")}
        onOpenReview={openReview}
        onSilenceTrim={(ids) => void batchSilenceTrim(ids)}
      />

      <TimelineFilterBar
        filters={filters}
        segments={segments}
        matchCount={filteredSegments.length}
        onChange={(patch) => setFilters((f) => ({ ...f, ...patch }))}
        onSelectSearchResult={(id, ms) => selectSegment(id, ms)}
      />

      <TimelineQcChecklist
        run={run}
        nle={nle}
        segments={segments}
        voLines={voLines}
        narrativePlan={narrativePlan}
        onJump={(id, ms) => selectSegment(id, ms)}
        onRestore={(id) => void patchSegment(id, { excluded: false, mark_redo: false }, "structural")}
        onOpenReview={() => openReview("qc_issue")}
      />

      <ReviewQueuePanel
        open={reviewOpen}
        filter={reviewFilter}
        queue={reviewQueue}
        index={reviewIndex}
        onClose={() => setReviewOpen(false)}
        onFilterChange={(f) => {
          setReviewFilter(f);
          setReviewIndex(0);
        }}
        onPrev={goReviewPrev}
        onNext={goReviewNext}
        onExclude={() => void patchSelectedSegment({ excluded: true }, "structural")}
        onRestore={() => void patchSelectedSegment({ excluded: false, mark_redo: false }, "structural")}
        onSnapTrim={() => void handleSnapTrimSelected()}
        onTighten={() => void handleTightenPauses()}
        onMarkRedo={() => void patchSelectedSegment({ mark_redo: true }, "structural")}
        onSkip={goReviewNext}
      />

      <ApplyEditsPanel
        nle={nle}
        runId={runId}
        segments={segments}
        voLines={voLines}
        chapterAnchorIds={chapterAnchors}
        assemblyDurationBefore={assemblyDurationBefore}
        assemblyDurationAfter={assembly?.timeline_duration_ms ?? null}
        previewAudioPath={
          assembly?.preview_audio && runId
            ? `/api/runs/${runId}/audio?path=${encodeURIComponent(assembly.preview_audio)}`
            : undefined
        }
        priorPreviewUrl={priorPreviewUrl}
        sticky
        onBeforeApply={(d) => {
          if (assembly?.preview_audio && runId) {
            setPriorPreviewUrl(
              `/api/runs/${runId}/audio?path=${encodeURIComponent(assembly.preview_audio)}`,
            );
          }
          setAssemblyDurationBefore(d);
        }}
        onApplied={() => {
          void loadAssembly();
          setMode("assembly");
        }}
      />

      <div className="timeline-main-layout">
        <div className="timeline-canvas">
          <TimelineMiniMap
            durationMs={durationMs}
            widthPx={widthPx}
            scrollLeftPx={scrollLeftPx}
            viewportWidthPx={viewportWidthPx}
            segmentSpans={minimapSpans}
            onScrollTo={(left) => {
              if (timelineScrollRef.current) {
                timelineScrollRef.current.scrollLeft = left;
                setScrollLeftPx(left);
              }
            }}
          />
          {mode === "source" ? (
            <SourceTimeline
              segments={segments}
              voLines={voLines}
              durationMs={durationMs}
              widthPx={widthPx}
              zoom={zoom}
              playheadMs={playheadMs}
              selectedSegmentId={selectedSegmentId}
              selectedSegmentIds={selectedSegmentIds}
              visibleSegmentIds={visibleSegmentIds}
              hideNonMatching={filters.hideNonMatching}
              snapEnabled={snapEnabled}
              waveform={waveform}
              chapters={chapters}
              markers={nle?.markers}
              scrollRef={timelineScrollRef}
              onSeek={seekTo}
              onSelect={selectSegment}
              onReorder={(a, b) => void reorderSegment(a, b)}
              onTrim={(id, s, e, snap) => void handleTrim(id, s, e, snap)}
              onContextAction={(id, action) => void handleContextAction(id, action)}
              onPlayheadDrag={seekTo}
              onScroll={setScrollLeftPx}
            />
          ) : assembly?.ready ? (
            <AssemblyTimeline
              assembly={assembly}
              widthPx={widthPx}
              playheadMs={playheadMs}
              selectedSegmentId={selectedSegmentId}
              onSeek={seekTo}
              onSelectSpeech={(segId, ms) => selectSegment(segId, ms)}
              onReorder={(a, b) => void reorderSegment(a, b)}
              onJumpToSource={(segId) => {
                const seg = segments.find((s) => s.segment_id === segId);
                setMode("source");
                if (seg) selectSegment(segId, seg.start_ms);
              }}
            />
          ) : (
            <p className="empty-state">
              {assembly?.reason || "Assembly timeline not ready — apply edits or run edl_flow1."}
            </p>
          )}
        </div>

        <div className="timeline-side-column">
          <SegmentInspector
            segment={selectedSegment}
            voLines={voLines}
            selectionOrder={selectionOrder}
            narrativePlan={narrativePlan}
            contentBrief={contentBrief}
            playheadMs={playheadMs}
            qcIssues={segmentQcIssues}
            onPatch={(p) => void patchSelectedSegment(p, "structural")}
            onTrim={(s, e, snap) => {
              if (selectedSegment?.segment_id) void handleTrim(selectedSegment.segment_id, s, e, snap);
            }}
            onSplit={() => void splitAtPlayhead()}
            onSnapTrim={() => void handleSnapTrimSelected()}
            onExpandSentence={() => void expandSelectedToSentence()}
            onOpenStageTab={() => setPipelineSubTab("stage")}
          />
          <EditHistoryPanel
            entries={history.entries}
            pointer={history.pointer}
            canUndo={history.canUndo}
            canRedo={history.canRedo}
            onUndo={() => void undo()}
            onRedo={() => void redo()}
            onRestore={(i) => void restoreHistoryAt(i)}
          />
        </div>
      </div>

      <TranscriptStrip
        words={words}
        playheadMs={playheadMs}
        focusRange={focusRange}
        segments={segments}
        lowThreshold={lowThreshold}
        followPlayback={followPlayback}
        onSeek={seekTo}
        onWordRangeSelect={(start, end) => {
          if (selectedSegment?.segment_id) void handleTrim(selectedSegment.segment_id, start, end, true);
        }}
        onExcludeSegment={() => void patchSelectedSegment({ excluded: true }, "structural")}
        onMarkRedo={() => void patchSelectedSegment({ mark_redo: true }, "structural")}
      />

      <TimelineTransport
        playheadMs={playheadMs}
        durationMs={activeDurationMs}
        playing={playing}
        playbackSpeed={playbackSpeed}
        loopSelection={loopSelection}
        followPlayback={followPlayback}
        hasSelection={!!selectedSegment}
        onTogglePlay={togglePlay}
        onSeek={seekTo}
        onSpeedChange={setPlaybackSpeed}
        onLoopChange={setLoopSelection}
        onFollowChange={setFollowPlayback}
        playerRef={playerRef}
        loopStartMs={selectedSegment?.start_ms}
        loopEndMs={selectedSegment?.end_ms}
      />

      <audio
        ref={playerRef}
        className="transcript-dock-audio-hidden"
        key={activeAudioPath}
        src={activeAudioPath}
        preload="metadata"
        onTimeUpdate={() => {
          if (playerRef.current) setPlayheadOnly(playerRef.current.currentTime * 1000);
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
    </div>
  );
}
