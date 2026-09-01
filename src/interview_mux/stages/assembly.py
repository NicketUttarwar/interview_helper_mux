from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from interview_mux.gates import check_edl_narrative_qc, check_edl_qc, check_narrative_qc
from interview_mux.operator_subprocess import run_command
from interview_mux.nle_state import (
    apply_nle_to_selection,
    load_nle,
    nle_has_operator_edits,
    segments_by_id_with_nle,
)
from interview_mux.operator_trace import logged_step
from interview_mux.prompt_validation import validate_edl
from interview_mux.run_context import RunContext


def _commit_edl_gap_report(ctx: RunContext, gap_report: dict) -> None:
    """Persist gap_report to the committed tree during EDL staging (glue promote contract)."""
    from interview_mux.write_staging import write_committed_json

    write_committed_json(ctx, "understanding/gap_report.json", gap_report, stage_key="edl")


def _segment_by_id(ctx: RunContext) -> dict[str, dict]:
    return segments_by_id_with_nle(ctx)


def _wav_duration_ms(path: Path) -> int:
    proc = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        label=f"ffprobe duration {path.name}",
        capture_output=True,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        raise RuntimeError(f"edl: unreadable VO duration: {path}")
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"edl: unreadable VO duration: {path}") from exc
    return max(0, int(seconds * 1000))


def resolve_vo_pickup_path(ctx: RunContext, line: dict) -> Path | None:
    """Resolve pickup WAV: matched → synthesized → clean → normalized → raw.

    Rejects forbidden backends and speech-QA failures so tone stubs never enter the EDL.
    """
    pickup = ctx.final_path("vo_pickup")
    matched = pickup / "matched"
    synthesized = pickup / "synthesized"
    clean = pickup / "clean"
    normalized = pickup / "normalized"
    lid = line.get("line_id", "")
    seg = line.get("targets_segment_id", "")
    bases: list[Path] = []
    for candidate in (matched, synthesized, clean, normalized, pickup):
        if candidate.is_dir():
            bases.append(candidate)
    if not bases:
        bases = [pickup]
    from interview_mux.vo_speech_qa import backend_allowed_for_vo, vo_passes_speech_qa
    from interview_mux.vo_synthesis_audit import synthesis_entry_for_line

    for base in bases:
        for key in (lid, seg):
            if not key:
                continue
            candidate = base / f"{key}.wav"
            if not candidate.is_file():
                continue
            entry = synthesis_entry_for_line(ctx, str(lid or seg))
            if isinstance(entry, dict):
                backend = str(entry.get("backend") or "")
                if backend and not backend_allowed_for_vo(backend):
                    continue
                if entry.get("qc_pass") is False:
                    continue
                from interview_mux.vo_synthesis_audit import (
                    synthesis_entry_matches_line,
                )

                matches, _reason = synthesis_entry_matches_line(ctx, line)
                if not matches:
                    continue
            elif base.name in {"synthesized", "matched"}:
                # Generated/matched audio without a script audit cannot prove it
                # still corresponds to the current artifact text.
                continue
            if not vo_passes_speech_qa(candidate):
                continue
            return candidate
    return None


def vo_pickup_relpath(ctx: RunContext, path: Path) -> str:
    try:
        rel = path.relative_to(ctx.run_dir).as_posix()
    except ValueError:
        return path.as_posix()
    # Writes during a staged stage land under .pending_writes/<stage>/… — committed
    # EDL/mix consumers must see the post-flush run-relative path.
    prefix = ".pending_writes/"
    if rel.startswith(prefix):
        rest = rel[len(prefix) :]
        if "/" in rest:
            rel = rest.split("/", 1)[1]
    return rel


def _normalize_vo_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _same_speaker_source_contiguous(
    prev: dict | None,
    curr: dict | None,
    *,
    gap_ms: int = 2500,
) -> bool:
    if not isinstance(prev, dict) or not isinstance(curr, dict):
        return False
    prev_spk = str(prev.get("speaker_id") or "").strip()
    curr_spk = str(curr.get("speaker_id") or "").strip()
    if not prev_spk or prev_spk != curr_spk:
        return False
    try:
        prev_end = int(prev.get("end_ms") or prev.get("source_end_ms") or 0)
        curr_start = int(curr.get("start_ms") or curr.get("source_start_ms") or 0)
    except (TypeError, ValueError):
        return False
    source_gap = curr_start - prev_end
    return -gap_ms <= source_gap <= gap_ms


def _gap_lines_for_segment(
    gap_report: dict | None,
    segment_id: str,
    placement: str,
    *,
    emitted_line_ids: set[str] | None = None,
    emitted_sentence_keys: set[str] | None = None,
) -> list[dict]:
    if not gap_report:
        return []
    out: list[dict] = []
    seen_ids = emitted_line_ids if emitted_line_ids is not None else set()
    seen_sentences = (
        emitted_sentence_keys if emitted_sentence_keys is not None else set()
    )
    from interview_mux.spoken_copy_guard import sentence_keys

    for line in gap_report.get("interviewer_lines") or []:
        if line.get("skipped_optional"):
            continue
        if line.get("targets_segment_id") != segment_id:
            continue
        if line.get("placement", "before") != placement:
            continue
        if line.get("delivery") != "record" and line.get("delivery") != "synthesize":
            continue
        lid = str(line.get("line_id") or "").strip()
        if lid and lid in seen_ids:
            continue
        line_sentence_keys = sentence_keys(str(line.get("text") or ""))
        # This is deliberately global, not scoped to a target or placement.
        # A repeated spoken sentence is unacceptable even if it was authored
        # for two different native segments — fail closed rather than silent-drop.
        collision = set(line_sentence_keys) & seen_sentences
        if collision:
            sample = next(iter(collision))
            raise ValueError(
                "EDL refused duplicate spoken sentence across VO lines "
                f"(line_id={lid or '?'}, targets={segment_id}, key={sample!r}). "
                "Regenerate or omit colliding synthetic copy before edl."
            )
        if lid:
            seen_ids.add(lid)
        seen_sentences.update(line_sentence_keys)
        out.append(line)
    return out


def _transition_after_segment(
    transitions: dict | None, after_segment_id: str, before_segment_id: str
) -> dict | None:
    if not transitions:
        return None
    for item in transitions.get("transitions") or []:
        if (
            item.get("after_segment_id") == after_segment_id
            and item.get("before_segment_id") == before_segment_id
        ):
            return item
    return None


def build_flow1_edl(
    *,
    selection: dict,
    segments_by_id: dict[str, dict],
    gap_report: dict | None = None,
    transitions: dict | None = None,
    resolve_vo_path: Callable[[dict], Path | None] | None = None,
    vo_relpath: Callable[[Path], str] | None = None,
    vo_duration_ms: Callable[[Path], int] | None = None,
    resolve_transition_path: Callable[[str, str], Path | None] | None = None,
    ideal_cuts: dict | list | None = None,
    transcript_words: list | None = None,
    max_keeper_ms: int | None = None,
    normalized_wav: Path | str | None = None,
    ctx: RunContext | None = None,
    verify_pair: Callable[[Path, Path], str | None] | None = None,
) -> dict:
    """Build Flow 1 EDL: speech order from selection, gap VO placements, transition anchors.

    When ``ideal_cuts`` / ``transcript_words`` are provided, speech clips use
    tightened air bounds (ideal window + complete-thought trim) instead of the
    full coarse segment slab. ``normalized_wav`` enables acoustic silence-valley
    micro-snaps at keeper edges.
    """
    from interview_mux.listenability_guards import air_pad_ms, listenability_guards_cfg
    from interview_mux.ideal_cuts import resolve_keeper_air_bounds

    ordered = list(selection.get("ordered_segment_ids") or [])
    clips: list[dict] = []
    gap_placements: list[dict] = []
    timeline_ms = 0
    missing_vo: list[str] = []
    missing_targets: list[str] = []
    missing_segments: list[str] = []
    omitted_unplayable: list[str] = []
    missing_transitions: list[str] = []
    suppressed_clone_adjacency: list[str] = []
    from interview_mux.clone_adjacency_verify import CloneAdjacencySession

    clone_adj = CloneAdjacencySession(ctx=ctx, verify_pair=verify_pair)
    air_cfg = listenability_guards_cfg()
    words = [w for w in (transcript_words or []) if isinstance(w, dict)]
    never_touch_intervals: list[tuple[int, int, str]] = []
    if ctx is not None:
        try:
            from interview_mux.media_ip_cta import never_touch_source_intervals

            never_touch_intervals = never_touch_source_intervals(ctx)
        except Exception:
            never_touch_intervals = []
    if max_keeper_ms is None:
        try:
            from interview_mux.ideal_cuts import ideal_cuts_cfg

            max_keeper_ms = int(ideal_cuts_cfg().get("max_cut_ms") or 180_000)
        except Exception:
            max_keeper_ms = 180_000

    def _append_air(
        kind: str,
        ref_dur: int,
        *,
        required_seam_hitch: bool = False,
        clone_adjacency_hitch: bool = False,
        preserve_planned_music: bool = False,
    ) -> None:
        nonlocal timeline_ms
        pad = air_pad_ms(ref_dur, kind=kind, cfg=air_cfg)
        if pad <= 0:
            return
        clip: dict = {
            "type": "silence",
            "air_kind": kind,
            "duration_ms": pad,
            "timeline_start_ms": timeline_ms,
        }
        if required_seam_hitch:
            clip["required_seam_hitch"] = True
            clip["preserve_planned_music"] = True
        if clone_adjacency_hitch:
            clip["clone_adjacency_hitch"] = True
            clip["preserve_planned_music"] = True
        if preserve_planned_music:
            clip["preserve_planned_music"] = True
        clips.append(clip)
        timeline_ms += pad

    def _same_answer_seam(after_sid: str, before_sid: str) -> bool:
        """True when adjacent keeps continue one answer — no chapter hitch air."""
        if not words:
            return False
        after = segments_by_id.get(after_sid) or {}
        before = segments_by_id.get(before_sid) or {}
        try:
            left_end = int(after.get("end_ms") or after.get("source_end_ms") or 0)
            right_start = int(before.get("start_ms") or before.get("source_start_ms") or 0)
        except (TypeError, ValueError):
            return False
        if left_end <= 0 or right_start <= 0:
            return False
        from interview_mux.gap_vo_prior_context import same_answer_continues

        return same_answer_continues(words, left_end, right_start)

    def _is_orientation(line: dict) -> bool:
        from interview_mux.opening_orientation import is_episode_orientation

        return is_episode_orientation(line)

    def _copy_hashes(line: dict) -> dict[str, str]:
        from interview_mux.spoken_copy_guard import (
            context_hash,
            evidence_for_line,
            script_hash,
        )

        return {
            "script_hash": script_hash(str(line.get("text") or "")),
            "context_hash": context_hash(evidence_for_line(line)),
        }

    def _append_opening_music_marker(ref_dur: int) -> None:
        nonlocal timeline_ms
        from interview_mux.opening_orientation import OPENING_MUSIC_AIR_KIND

        pad = air_pad_ms(ref_dur, kind="chapter_hinge", cfg=air_cfg)
        clips.append(
            {
                "type": "silence",
                "air_kind": OPENING_MUSIC_AIR_KIND,
                "duration_ms": max(0, pad),
                "timeline_start_ms": timeline_ms,
                "preserve_planned_music": True,
            }
        )
        timeline_ms += max(0, pad)

    if gap_report:
        for line in gap_report.get("interviewer_lines") or []:
            if line.get("skipped_optional"):
                continue
            if line.get("delivery") != "record":
                continue
            target = line.get("targets_segment_id", "")
            if target and target not in ordered:
                missing_targets.append(target)

    duration_fn = vo_duration_ms or _wav_duration_ms
    emitted_line_ids: set[str] = set()
    emitted_sentence_keys: set[str] = set()
    prev_speech_end_ms: int | None = None

    def _last_non_silence_type() -> str:
        for clip in reversed(clips):
            ctype = str(clip.get("type") or "")
            if ctype and ctype != "silence":
                return ctype
        return ""

    for idx, sid in enumerate(ordered):
        seg = segments_by_id.get(sid)
        if not seg:
            missing_segments.append(sid)
            continue

        prev_sid = ordered[idx - 1] if idx > 0 else ""
        prev_seg = segments_by_id.get(prev_sid) if prev_sid else None
        skip_before_vo = _same_speaker_source_contiguous(prev_seg, seg)
        nxt = ordered[idx + 1] if idx + 1 < len(ordered) else ""
        next_before_vo = bool(
            nxt
            and _gap_lines_for_segment(
                gap_report,
                nxt,
                "before",
                emitted_line_ids=set(emitted_line_ids),
                emitted_sentence_keys=set(emitted_sentence_keys),
            )
        )

        before_lines = _gap_lines_for_segment(
            gap_report,
            sid,
            "before",
            emitted_line_ids=emitted_line_ids,
            emitted_sentence_keys=emitted_sentence_keys,
        )
        if skip_before_vo:
            # Contiguous same-speaker source usually needs no seam hinge, but
            # authoritative nugget layups (and episode orientation) must still air.
            before_lines = [
                ln
                for ln in before_lines
                if str(ln.get("origin") or "") == "nugget_layup" or _is_orientation(ln)
            ]
        # One host turn per seam: never stack a second synthetic after VO/transition.
        # Orientation may still air on the opening native only.
        if _last_non_silence_type() in {"vo_pickup", "transition"}:
            if idx == 0:
                before_lines = [ln for ln in before_lines if _is_orientation(ln)]
            else:
                before_lines = []

        # Opening grammar pin: orientation must stay within the early audible window.
        # Straight: orientation first among before-VO. Cold open: defer hook before-VO
        # until after hook speech + opening_music + orientation.
        cold_open_hook = False
        if idx == 0 and gap_report:
            for _oln in gap_report.get("interviewer_lines") or []:
                if (
                    isinstance(_oln, dict)
                    and _is_orientation(_oln)
                    and not _oln.get("skipped_optional")
                    and str(_oln.get("targets_segment_id") or "") == sid
                    and str(_oln.get("placement") or "before") == "after"
                ):
                    cold_open_hook = True
                    break
        before_lines = sorted(
            before_lines, key=lambda ln: (0 if _is_orientation(ln) else 1)
        )
        deferred_before: list[dict] = []
        if cold_open_hook and before_lines:
            deferred_before = [ln for ln in before_lines if not _is_orientation(ln)]
            before_lines = [ln for ln in before_lines if _is_orientation(ln)]

        def _emit_vo_line(line: dict, *, placement: str) -> None:
            nonlocal timeline_ms
            voice_speaker_id = str(line.get("voice_speaker_id") or "").strip()
            target_speaker_id = str(seg.get("speaker_id") or "").strip()
            prev_speaker_id = (
                str((prev_seg or {}).get("speaker_id") or "").strip() if prev_seg else ""
            )
            id_adjacent = bool(
                voice_speaker_id
                and (
                    voice_speaker_id == target_speaker_id
                    or (placement == "before" and voice_speaker_id == prev_speaker_id)
                )
            )
            if (
                id_adjacent
                and not bool(line.get("clone_adjacency_exempt"))
                and not _is_orientation(line)
            ):
                target = dict(seg)
                target.setdefault("segment_id", sid)
                after = dict(prev_seg) if isinstance(prev_seg, dict) else None
                if after is not None:
                    after.setdefault("segment_id", prev_sid)
                vo_key = str(line.get("line_id") or sid)
                if clone_adj.decide(
                    kind="vo_pickup",
                    key=vo_key,
                    clone_voice_id=voice_speaker_id,
                    target=target,
                    after=after if placement == "before" else None,
                ):
                    suppressed_clone_adjacency.append(vo_key)
                    return
            vo_path = resolve_vo_path(line) if resolve_vo_path else None
            rel: str | None = None
            dur = 0
            if vo_path is None or not vo_path.is_file():
                missing_vo.append(line.get("line_id") or sid)
                if (
                    str(line.get("delivery") or "").lower() == "synthesize"
                    or _is_orientation(line)
                    or bool(line.get("required"))
                ):
                    return
            else:
                rel = vo_relpath(vo_path) if vo_relpath else vo_path.as_posix()
                dur = duration_fn(vo_path)
            # Cold open: music marker precedes orientation VO.
            if placement == "after" and _is_orientation(line):
                est_ms = int(float(line.get("estimated_duration_sec") or 0) * 1000)
                _append_opening_music_marker(max(dur, est_ms, 1000))
            clip = {
                "type": "vo_pickup",
                "line_id": line.get("line_id"),
                "targets_segment_id": sid,
                "placement": placement,
                "voice_speaker_id": voice_speaker_id,
                "clone_adjacency_exempt": bool(
                    line.get("clone_adjacency_exempt") or _is_orientation(line)
                ),
                "gap_type": line.get("gap_type"),
                "line_category": line.get("line_category"),
                "episode_orientation": bool(line.get("episode_orientation")),
                "opening_sequence": line.get("opening_sequence"),
                "allow_music_bed_overlap": bool(line.get("allow_music_bed_overlap")),
                **_copy_hashes(line),
                "source_path": rel,
                "duration_ms": dur,
                "timeline_start_ms": timeline_ms,
            }
            clips.append(clip)
            gap_placements.append(
                {
                    "line_id": line.get("line_id"),
                    "targets_segment_id": sid,
                    "placement": placement,
                    "timeline_start_ms": timeline_ms,
                }
            )
            timeline_ms += dur
            # Straight open: music marker follows orientation VO.
            if placement == "before" and _is_orientation(line):
                est_ms = int(float(line.get("estimated_duration_sec") or 0) * 1000)
                _append_opening_music_marker(max(dur, est_ms, 1000))
            elif dur > 0:
                _append_air("after_vo", dur)

        for line in before_lines:
            _emit_vo_line(line, placement="before")

        # Native-open omit: still reserve the opening-music window so theme can
        # bed under the hosts' own greeting (music → body).
        if idx == 0 and not cold_open_hook:
            meta = (
                (gap_report or {}).get("opening_orientation")
                if isinstance(gap_report, dict)
                else None
            )
            omitted = isinstance(meta, dict) and (
                bool(meta.get("omitted")) or meta.get("required") is False
            )
            already_opening_music = any(
                str(clip.get("air_kind") or "") == "opening_music" for clip in clips
            )
            if omitted and not already_opening_music:
                _append_opening_music_marker(
                    max(int(seg.get("end_ms") or 0) - int(seg.get("start_ms") or 0), 1000)
                )

        speech_start = int(seg["start_ms"])
        speech_end = int(seg["end_ms"])
        air_meta: dict = {}
        next_keeper_start = None
        if nxt:
            nxt_seg = segments_by_id.get(nxt)
            if isinstance(nxt_seg, dict) and nxt_seg.get("start_ms") is not None:
                next_keeper_start = int(nxt_seg["start_ms"])
        if ideal_cuts is not None or words:
            from interview_mux.media_ip_cta import never_touch_end_cap_ms

            nt_cap = never_touch_end_cap_ms(speech_start, never_touch_intervals)
            speech_start, speech_end = resolve_keeper_air_bounds(
                source_start_ms=speech_start,
                source_end_ms=speech_end,
                cuts_doc=ideal_cuts if isinstance(ideal_cuts, (dict, list)) else None,
                words=words or None,
                segment_id=str(sid),
                max_keep_ms=max_keeper_ms,
                next_keeper_start_ms=next_keeper_start,
                prev_keeper_end_ms=prev_speech_end_ms,
                never_touch_cap_ms=nt_cap,
                meta_out=air_meta,
                wav_path=normalized_wav,
            )
        if words:
            from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge
            from interview_mux.ideal_cuts import last_complete_thought_end_ms

            span = " ".join(
                str(w.get("text") or "")
                for w in words
                if isinstance(w, dict)
                and speech_start <= int(w.get("start_ms") or 0) < speech_end
            ).strip()
            if span and not is_legal_conceptual_hinge(
                span, words=words, end_ms=speech_end
            ):
                fixed = last_complete_thought_end_ms(
                    words, start_ms=speech_start, end_ms=speech_end
                )
                if fixed is not None and fixed - speech_start >= 400:
                    speech_end = int(fixed)
        speech_dur = max(0, speech_end - speech_start)
        if words and speech_dur < 5000:
            from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

            span = " ".join(
                str(w.get("text") or "")
                for w in words
                if isinstance(w, dict)
                and speech_start <= int(w.get("start_ms") or 0) < speech_end
            ).strip()
            b0 = air_meta.get("before_start_ms")
            b1 = air_meta.get("before_end_ms")
            if span and not is_legal_conceptual_hinge(
                span, words=words, end_ms=speech_end
            ):
                if b0 is not None and b1 is not None and int(b1) - int(b0) >= 2000:
                    speech_start, speech_end = int(b0), int(b1)
                    speech_dur = max(0, speech_end - speech_start)
                    air_meta["air_bound_reason"] = (
                        str(air_meta.get("air_bound_reason") or "") + "+before_window_hanging_rescue"
                    )
        if never_touch_intervals:
            from interview_mux.media_ip_cta import clamp_source_away_from_never_touch

            clamped_s, clamped_e, nt_notes = clamp_source_away_from_never_touch(
                speech_start, speech_end, never_touch_intervals
            )
            if nt_notes:
                speech_start, speech_end = clamped_s, clamped_e
                prior = str(air_meta.get("air_bound_reason") or "")
                air_meta["air_bound_reason"] = (
                    f"{prior}+never_touch_clamp" if prior else "never_touch_clamp"
                )
        speech_dur = max(0, speech_end - speech_start)
        if speech_dur < 400:
            omitted_unplayable.append(sid)
            continue
        if clips and str(clips[-1].get("type") or "") == "silence":
            pass
        elif any(c.get("type") == "vo_pickup" for c in clips[-3:]):
            _append_air("before_answer", speech_dur)
        speech_clip = {
            "segment_id": sid,
            "source_start_ms": speech_start,
            "source_end_ms": speech_end,
            "timeline_start_ms": timeline_ms,
            "duration_ms": speech_dur,
            "type": "speech",
        }
        if air_meta:
            speech_clip["air_bound_reason"] = air_meta.get("air_bound_reason")
            if air_meta.get("ideal_window_id"):
                speech_clip["air_bound_ideal_window_id"] = air_meta.get("ideal_window_id")
            speech_clip["air_bound_before_ms"] = [
                air_meta.get("before_start_ms"),
                air_meta.get("before_end_ms"),
            ]
            speech_clip["air_bound_after_ms"] = [
                air_meta.get("after_start_ms"),
                air_meta.get("after_end_ms"),
            ]
        clips.append(speech_clip)
        timeline_ms += speech_dur
        prev_speech_end_ms = speech_end

        after_lines = _gap_lines_for_segment(
            gap_report,
            sid,
            "after",
            emitted_line_ids=emitted_line_ids,
            emitted_sentence_keys=emitted_sentence_keys,
        )
        # Prefer a before-VO layup on the next clip over an after-VO on this one.
        # Keep episode orientation — cold-open grammar requires it after the hook.
        if next_before_vo:
            after_lines = [ln for ln in after_lines if _is_orientation(ln)]
        after_lines = sorted(
            after_lines, key=lambda ln: (0 if _is_orientation(ln) else 1)
        )

        for line in after_lines:
            _emit_vo_line(line, placement="after")

        # Cold-open: hook before-VO deferred until after orientation.
        for line in deferred_before:
            _emit_vo_line(line, placement="before")

        if idx + 1 < len(ordered):
            nxt = ordered[idx + 1]
            tr = _transition_after_segment(transitions, sid, nxt)
            suppressed_transition = False
            if tr:
                from interview_mux.gap_framing import choose_seam_synthetic

                choice = choose_seam_synthetic(
                    sid,
                    nxt,
                    gap_report=gap_report,
                    transitions_doc=transitions,
                )
                if str(choice.get("kind") or "") == "layup":
                    tr = None
                elif _last_non_silence_type() == "vo_pickup":
                    tr = None
                else:
                    already_vo = any(
                        isinstance(c, dict)
                        and c.get("type") == "vo_pickup"
                        and str(c.get("targets_segment_id") or "") == str(nxt)
                        for c in clips
                    )
                    if already_vo:
                        tr = None
            if tr:
                transition_voice = str(tr.get("voice_speaker_id") or "").strip()
                after_seg = dict(segments_by_id.get(sid) or {})
                after_seg.setdefault("segment_id", sid)
                before_seg = dict(segments_by_id.get(nxt) or {})
                before_seg.setdefault("segment_id", nxt)
                # Empty voice still runs decide when a clone plan is locked so
                # unvoiced transitions next to the clone source are hitch-replaced.
                clone_voice = transition_voice
                if not clone_voice and ctx is not None:
                    try:
                        if ctx.artifact_exists("understanding/speaker_delivery_plan.json"):
                            plan = ctx.read_json(
                                "understanding/speaker_delivery_plan.json"
                            )
                            clone_voice = str(
                                (plan or {}).get("clone_speaker_id") or ""
                            ).strip()
                    except Exception:
                        clone_voice = ""
                if not clone_voice and ctx is not None:
                    try:
                        from interview_mux.source_topology import (
                            pickup_eligible_speaker_id,
                        )

                        clone_voice = str(
                            pickup_eligible_speaker_id(ctx) or ""
                        ).strip()
                    except Exception:
                        clone_voice = ""
                if clone_voice and clone_adj.decide(
                    kind="transition",
                    key=f"transition:{sid}->{nxt}",
                    clone_voice_id=clone_voice,
                    after=after_seg,
                    before=before_seg,
                ):
                    suppressed_clone_adjacency.append(f"transition:{sid}->{nxt}")
                    tr = None
                    suppressed_transition = True
            if tr:
                text = str(tr.get("text") or "")
                from interview_mux.spoken_copy_guard import script_hash

                tr_path = (
                    resolve_transition_path(sid, nxt) if resolve_transition_path else None
                )
                tr_rel = None
                tr_dur = 0
                if tr_path is not None and tr_path.is_file():
                    tr_rel = vo_relpath(tr_path) if vo_relpath else tr_path.as_posix()
                    tr_dur = duration_fn(tr_path)
                elif text.strip():
                    missing_transitions.append(f"{sid}->{nxt}")
                clips.append(
                    {
                        "type": "transition",
                        "after_segment_id": sid,
                        "before_segment_id": nxt,
                        "text": text,
                        "transition_type": tr.get("type", "bridge"),
                        "voice_speaker_id": tr.get("voice_speaker_id"),
                        "duration_ms": tr_dur,
                        "timeline_start_ms": timeline_ms,
                        "script_hash": script_hash(text),
                        **({"source_path": tr_rel} if tr_rel else {}),
                    }
                )
                timeline_ms += tr_dur
                if not _same_answer_seam(sid, nxt):
                    if tr_dur > 0:
                        _append_air("chapter_hinge", tr_dur)
                    else:
                        _append_air("chapter_hinge", speech_dur)
            else:
                # No spoken transition: still need audible chapter/reorder hitch
                # unless this is the same answer continuing on tape.
                needs_hitch = suppressed_transition
                if not needs_hitch:
                    from interview_mux.reorder_bridges import build_reorder_bridges

                    bridges = build_reorder_bridges([sid, nxt], segments_by_id)
                    needs_hitch = bool(bridges.get("pairs"))
                if needs_hitch and not _same_answer_seam(sid, nxt):
                    _append_air(
                        "chapter_hinge",
                        max(int(speech_dur), 1000),
                        required_seam_hitch=True,
                        clone_adjacency_hitch=bool(suppressed_transition),
                    )

    if omitted_unplayable and ctx is not None:
        try:
            from interview_mux.media_ip_cta import _omit_unplayable_keeps_from_selection

            drop_reasons = {sid: "never_touch_unplayable" for sid in omitted_unplayable}
            _omit_unplayable_keeps_from_selection(ctx, omitted_unplayable, drop_reasons)
        except Exception:
            pass
    air_ordered = [s for s in ordered if s not in set(omitted_unplayable)]

    return {
        "version": 1,
        "ordered_segment_ids": air_ordered,
        "clips": clips,
        "gap_placements": gap_placements,
        "timeline_duration_ms": timeline_ms,
        "gap_report_line_count": len((gap_report or {}).get("interviewer_lines") or []),
        "vo_pickup_clip_count": sum(1 for c in clips if c.get("type") == "vo_pickup"),
        "transition_clip_count": sum(1 for c in clips if c.get("type") == "transition"),
        "silence_clip_count": sum(1 for c in clips if c.get("type") == "silence"),
        "warnings": {
            "missing_vo_files": sorted(set(missing_vo)),
            "gap_targets_not_in_selection": sorted(set(missing_targets)),
            "missing_segment_lookups": sorted(set(missing_segments)),
            "missing_transition_audio": sorted(set(missing_transitions)),
            "suppressed_clone_adjacency": sorted(set(suppressed_clone_adjacency)),
            "clone_adjacency_id_mismatch_kept": sorted(
                set(k for k in clone_adj.kept_despite_id() if k)
            ),
        },
        "mux_scope": "full_mix",
        "_clone_adjacency_verify": clone_adj.report(),
    }


def resync_required_synthesize_wavs(ctx: RunContext, gap_report: dict) -> list[str]:
    """Re-speak active synthesize lines whose WAV is missing or hash-stale. Once.

    When gap framing / chatterbox is active, every non-skipped synthesize line is
    eligible (not only orientation). Otherwise only orientation/required.
    """
    from interview_mux.opening_orientation import is_episode_orientation
    from interview_mux.spoken_copy_guard import script_hash
    from interview_mux.vo_synthesis_audit import synthesis_entry_matches_line
    from interview_mux import s2s_runner

    framing_active = False
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled, resolve_gap_vo_delivery

        framing_active = gap_framing_enabled(ctx) and resolve_gap_vo_delivery(ctx) in {
            "chatterbox",
            "synthesize",
            "voice_clone",
        }
    except Exception:
        framing_active = False

    notes: list[str] = []
    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict) or line.get("skipped_optional"):
            continue
        if str(line.get("delivery") or "").lower() != "synthesize":
            continue
        requiredish = is_episode_orientation(line) or bool(line.get("required"))
        if not framing_active and not requiredish:
            continue
        path = resolve_vo_pickup_path(ctx, line)
        matches, reason = synthesis_entry_matches_line(ctx, line)
        if path is not None and path.is_file() and matches:
            continue
        lid = str(line.get("line_id") or "")
        try:
            s2s_runner.synthesize_line(ctx, line, mode="synthesize")
            notes.append(lid)
        except Exception as exc:
            raise RuntimeError(
                f"edl: synthesize WAV stale/missing (line_id={lid} "
                f"reason={reason} path={path} "
                f"script_hash={script_hash(str(line.get('text') or ''))}): {exc}"
            ) from exc
        path2 = resolve_vo_pickup_path(ctx, line)
        matches2, reason2 = synthesis_entry_matches_line(ctx, line)
        if path2 is None or not path2.is_file() or not matches2:
            raise RuntimeError(
                f"edl: synthesize WAV stale/missing (line_id={lid} "
                f"reason={reason2} path={path2} "
                f"script_hash={script_hash(str(line.get('text') or ''))})"
            )
    return notes


def _prepare_locked_selection(ctx: RunContext, selection: dict) -> dict:
    from interview_mux.artifact_repairs import (
        _segment_is_blank_or_unusable,
        reconcile_ordered_vs_excluded,
    )

    selection = reconcile_ordered_vs_excluded(
        selection if isinstance(selection, dict) else {}
    )
    order = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
    cleaned = [s for s in order if not _segment_is_blank_or_unusable(ctx, s)]
    if cleaned != order:
        have = {
            str(r.get("segment_id") if isinstance(r, dict) else r)
            for r in (selection.get("excluded_segment_ids") or [])
        }
        excl = list(selection.get("excluded_segment_ids") or [])
        for sid in order:
            if sid in cleaned or sid in have:
                continue
            excl.append({"segment_id": sid, "reason": "blank_or_unusable_answer_audio"})
            have.add(sid)
        selection["ordered_segment_ids"] = cleaned
        selection["excluded_segment_ids"] = excl
        keep = set(cleaned)
        for ch in selection.get("chapters") or []:
            if isinstance(ch, dict):
                ch["segment_ids"] = [
                    str(x) for x in (ch.get("segment_ids") or []) if str(x) in keep
                ]
        selection = reconcile_ordered_vs_excluded(selection)
    return selection


def run_edl(ctx: RunContext) -> None:
    if ctx.artifact_exists("master/edl_narrative_audit.json"):
        audit = ctx.read_json("master/edl_narrative_audit.json")
        if str(audit.get("verdict", "")).strip().lower() == "fail":
            raise SystemExit(
                "edl_narrative_audit verdict is fail — fix blocking issues and re-run "
                "edl_narrative_audit before edl."
            )
    check_narrative_qc(ctx, stage="edl", require_selection=True)

    soft = False
    with logged_step("edl/load_inputs", ctx=ctx, stage="edl"):
        try:
            from interview_mux.media_ip_cta import heal_nle_unplayable_keep_overrides

            heal_nle_unplayable_keep_overrides(ctx)
        except Exception:
            pass
        selection = ctx.read_json("master/selection.json")
        from interview_mux.artifact_repairs import reconcile_ordered_vs_excluded

        selection = reconcile_ordered_vs_excluded(
            selection if isinstance(selection, dict) else {}
        )
        ctx.write_json("master/selection.json", selection)
        nle = load_nle(ctx)
        by_id = _segment_by_id(ctx)
        if nle_has_operator_edits(nle):
            selection = apply_nle_to_selection(
                selection, nle, segments_by_id=by_id
            )
            ctx.write_json("master/selection.json", selection)
            ordered = selection.get("ordered_segment_ids") or []
            excluded = selection.get("excluded_segment_ids") or []
            ctx.log(
                f"EDL: applied NLE edits — {len(ordered)} segments, "
                f"{len(excluded)} excluded.",
                level="info",
                stage="edl",
            )
        try:
            from interview_mux.air_script import enforce_air_script_omits
            from interview_mux.mastering_plan_loader import load_plan_raw

            if load_plan_raw(ctx):
                selection = enforce_air_script_omits(ctx, selection)
                ctx.write_json("master/selection.json", selection)
        except Exception as exc:
            ctx.log(f"edl: air_script omit bind skipped: {exc}", level="warning", stage="edl")
        gap_report = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else None
        )
        if isinstance(gap_report, dict):
            try:
                from interview_mux.artifact_repairs import repair_gap_report

                repaired, notes = repair_gap_report(ctx, gap_report)
                if notes:
                    ctx.write_json("understanding/gap_report.json", repaired)
                    ctx.log(
                        f"edl: repaired gap_report before build ({len(notes)} note(s))",
                        level="info",
                        stage="edl",
                    )
                gap_report = repaired
            except Exception as exc:
                ctx.log(f"edl: gap_report repair skipped: {exc}", level="warning", stage="edl")
            from interview_mux.opening_orientation import ensure_episode_orientation

            current_order = [
                str(x) for x in (selection.get("ordered_segment_ids") or []) if x
            ]
            gap_report, opening_actions = ensure_episode_orientation(
                ctx, gap_report, current_order
            )
            if opening_actions:
                ctx.write_json("understanding/gap_report.json", gap_report)
                ctx.log(
                    f"edl: opening orientation guard applied {len(opening_actions)} action(s)",
                    level="info",
                    stage="edl",
                    detail=opening_actions,
                )
            from interview_mux.opening_orientation import retarget_orientation_to_open

            synced = retarget_orientation_to_open(ctx)
            if synced:
                if ctx.artifact_exists("understanding/gap_report.json"):
                    gap_report = ctx.read_json("understanding/gap_report.json")
                ctx.log(
                    f"edl: orientation targets synced {synced}",
                    level="info",
                    stage="edl",
                )
            try:
                from interview_mux.air_script import (
                    filter_gap_lines_for_air_script,
                    persist_air_script_omits_on_gap_report,
                )
                from interview_mux.mastering_plan_loader import load_plan_raw

                omitted = persist_air_script_omits_on_gap_report(ctx)
                if omitted:
                    ctx.log(
                        f"edl: persisted {omitted} air_script VO omit(s) on gap_report",
                        level="info",
                        stage="edl",
                    )
                filtered = filter_gap_lines_for_air_script(
                    gap_report if isinstance(gap_report, dict) else None,
                    load_plan_raw(ctx),
                )
                if isinstance(filtered, dict):
                    gap_report = filtered
            except Exception as exc:
                ctx.log(f"edl: air_script VO filter skipped: {exc}", level="warning", stage="edl")
            resynced = resync_required_synthesize_wavs(ctx, gap_report)
            if resynced:
                ctx.log(
                    f"edl: re-synthesized stale required VO {resynced}",
                    level="info",
                    stage="edl",
                )
        from interview_mux.nugget_layup import (
            adopt_layup_plan_to_selection,
            assert_gap_report_layup_authority,
            assert_layup_fresh_vs_selection,
            dedupe_gap_report_nugget_claims,
        )

        # Air copy is about to be cut — refuse a lay-up plan built for a
        # different order, or a body another writer rewrote.
        if isinstance(gap_report, dict):
            gap_report, dedupe_notes = dedupe_gap_report_nugget_claims(gap_report)
            if dedupe_notes:
                ctx.write_json("understanding/gap_report.json", gap_report)
                ctx.log(
                    f"edl: deduped {len(dedupe_notes)} overlapping nugget claim(s)",
                    level="warning",
                    stage="edl",
                )
        selection = _prepare_locked_selection(ctx, selection)
        ctx.write_json("master/selection.json", selection)
        try:
            from interview_mux.nugget_layup import PLAN_REL

            if ctx.artifact_exists(PLAN_REL):
                adopt_layup_plan_to_selection(ctx, persist=True, stage="edl")
        except Exception:
            pass
        assert_layup_fresh_vs_selection(ctx, stage="edl")
        assert_gap_report_layup_authority(
            ctx, gap_report if isinstance(gap_report, dict) else None, stage="edl"
        )
        transitions = (
            ctx.read_json("master/transitions.json")
            if ctx.artifact_exists("master/transitions.json")
            else {"transitions": []}
        )
        from interview_mux.order_hash import bump_order_lock
        from interview_mux.seam_glue import ensure_seam_glue

        ordered = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
        selection = bump_order_lock(selection, source="edl")
        ctx.write_json("master/selection.json", selection)

        soft = False
        try:
            meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
            from interview_mux.e2e_soft import e2e_soft_enabled

            # Soft seams only from explicit waive / e2e flag — not mere NLE presence.
            if e2e_soft_enabled(meta=meta if isinstance(meta, dict) else None) and bool(
                (meta or {}).get("e2e_soft_junction_residuals")
            ):
                soft = True
            if isinstance(meta, dict) and meta.get("nle_waive_naked_seams"):
                soft = True
        except Exception:
            pass
        _bridges, transitions, completeness = ensure_seam_glue(
            ctx,
            ordered=ordered,
            segments_by_id=by_id,
            gap_report=gap_report if isinstance(gap_report, dict) else None,
            transitions=transitions if isinstance(transitions, dict) else None,
            soft=soft,
        )
        try:
            from interview_mux.air_script import filter_transitions_for_air_script
            from interview_mux.mastering_plan_loader import load_plan_raw

            transitions = filter_transitions_for_air_script(
                transitions if isinstance(transitions, dict) else None,
                load_plan_raw(ctx),
            ) or transitions
            if isinstance(transitions, dict):
                ctx.write_json(
                    "master/transitions.json",
                    transitions,
                    stage_key="transitions",
                )
        except Exception as trans_exc:
            ctx.log(f"edl: air_script transition filter skipped: {trans_exc}", level="warning", stage="edl")
        if soft and not completeness.get("complete"):
            ctx.log(
                f"bridge_completeness soft: "
                f"{completeness.get('missing_count')} missing — shipping",
                level="warning",
                stage="edl",
                detail=completeness.get("missing", [])[:6],
            )

    from interview_mux.air_order_integrity import audit_and_report

    audit_and_report(ctx, stage="edl", repair=False)

    with logged_step("edl/synthesize_transitions", ctx=ctx, stage="edl"):
        from interview_mux.transition_vo import (
            assert_required_bridge_synth_ok,
            assert_spoken_transitions_audible,
            resolve_transition_wav,
            resync_spoken_transitions,
            synthesize_spoken_transitions,
        )

        try:
            tr_notes = resync_spoken_transitions(ctx, fail_closed=False)
            if tr_notes:
                ctx.log(
                    f"edl: re-synthesized stale transitions {tr_notes[:6]}",
                    level="info",
                    stage="edl",
                )
        except RuntimeError:
            ctx.log("edl: resync raised; continuing with dangling-path lint", level="warning", stage="edl")
        synth_rows = synthesize_spoken_transitions(ctx)
        if synth_rows:
            failed = [r for r in synth_rows if r.get("ok") is False]
            if failed:
                ctx.log(
                    f"EDL: {len(failed)} transition synth failure(s)",
                    level="warning",
                    stage="edl",
                    detail={"failed": failed[:6]},
                )
            assert_required_bridge_synth_ok(ctx, synth_rows)

        # Synth stamps voice_speaker_id on disk; build must see that voice so
        # clone-adjacency suppress can hitch-replace instead of shipping a
        # clone-next-to-native transition clip (edl_narrative_qc thrash).
        if ctx.artifact_exists("master/transitions.json"):
            refreshed = ctx.read_json("master/transitions.json")
            if isinstance(refreshed, dict):
                transitions = refreshed

    with logged_step("edl/build_edl", ctx=ctx, stage="edl"):
        from interview_mux.order_hash import copy_order_lock, stamp_order_hash
        from interview_mux.ideal_cuts import load_air_bound_inputs

        selection = _prepare_locked_selection(ctx, selection)
        ctx.write_json("master/selection.json", selection)

        ideal_cuts_doc, transcript_words = load_air_bound_inputs(ctx)
        wav_path = None
        try:
            wav_path = ctx.read_path("ingest", "normalized.wav")
        except Exception:
            wav_path = None
        edl = build_flow1_edl(
            selection=selection,
            segments_by_id=by_id,
            gap_report=gap_report,
            transitions=transitions,
            resolve_vo_path=lambda line: resolve_vo_pickup_path(ctx, line),
            vo_relpath=lambda p: vo_pickup_relpath(ctx, p),
            resolve_transition_path=lambda a, b: resolve_transition_wav(ctx, a, b),
            ideal_cuts=ideal_cuts_doc,
            transcript_words=transcript_words,
            normalized_wav=wav_path,
            ctx=ctx,
        )
        verify_report = edl.pop("_clone_adjacency_verify", None)
        if isinstance(verify_report, dict):
            from interview_mux.clone_adjacency_verify import persist_clone_adjacency_verify

            persist_clone_adjacency_verify(ctx, verify_report)
        edl = copy_order_lock(selection, stamp_order_hash(edl))
        try:
            from interview_mux.gap_vo_gates import gap_framing_enabled
            from interview_mux.opening_orientation import (
                is_episode_orientation,
                orientation_omitted,
                validate_opening_orientation,
            )

            active_framing_lines = [
                line
                for line in ((gap_report or {}).get("interviewer_lines") or [])
                if isinstance(line, dict) and not line.get("skipped_optional")
            ]
            if gap_framing_enabled(ctx) and (
                active_framing_lines
                or orientation_omitted(gap_report if isinstance(gap_report, dict) else None)
            ):
                from interview_mux.spoken_copy_guard import script_hash

                missing = set((edl.get("warnings") or {}).get("missing_vo_files") or [])
                for line in active_framing_lines:
                    if not is_episode_orientation(line):
                        continue
                    lid = str(line.get("line_id") or "")
                    if lid in missing:
                        raise RuntimeError(
                            f"edl: orientation WAV stale/missing (line_id={lid} "
                            f"script_hash={script_hash(str(line.get('text') or ''))})"
                        )
                opening_errors = validate_opening_orientation(
                    gap_report=gap_report if isinstance(gap_report, dict) else None,
                    edl=edl,
                )
                if opening_errors:
                    raise RuntimeError(
                        "edl: opening orientation contract failed: "
                        + "; ".join(opening_errors)
                    )
        except ImportError:
            pass

    warnings = edl.get("warnings") or {}
    if warnings.get("missing_segment_lookups"):
        missing = sorted(set(warnings["missing_segment_lookups"]))
        raise RuntimeError(
            f"edl: ordered_segment_ids missing from manifest/NLE lookup: {missing}"
        )
    if warnings.get("missing_vo_files"):
        missing = sorted(set(warnings["missing_vo_files"]))
        skipped_ids: set[str] = set()
        if gap_report:
            from interview_mux.gates import vo_gap_line_effectively_optional

            for line in gap_report.get("interviewer_lines") or []:
                if not isinstance(line, dict):
                    continue
                if not (line.get("skipped_optional") or vo_gap_line_effectively_optional(ctx, line)):
                    continue
                skipped_ids.add(str(line.get("line_id") or ""))
                skipped_ids.add(str(line.get("targets_segment_id") or ""))
        missing = [mid for mid in missing if mid not in skipped_ids]
        if missing:
            raise RuntimeError(f"edl: gap VO lines missing WAV: {missing}")
    if warnings.get("gap_targets_not_in_selection"):
        ctx.log(
            f"EDL: gap targets not in selection order: "
            f"{warnings['gap_targets_not_in_selection']}",
            level="warning",
            stage="edl",
        )

    vo_n = edl.get("vo_pickup_clip_count", 0)
    ctx.log(
        f"EDL built: {len(edl.get('clips') or [])} events, "
        f"{vo_n} vo_pickup, timeline {edl.get('timeline_duration_ms')} ms "
        f"(mix: speech + VO + SDP overlays)",
        level="success",
        stage="edl",
    )
    from interview_mux.transition_vo import lint_edl_vo_source_paths

    edl = lint_edl_vo_source_paths(ctx, edl)
    assert_spoken_transitions_audible(ctx, edl)
    check_edl_qc(ctx, stage="edl", edl=edl, strict=True, gap_report=gap_report)
    check_edl_narrative_qc(ctx, stage="edl", edl=edl)

    with logged_step("edl/validate_write", ctx=ctx, stage="edl"):
        edl_errors = validate_edl(edl)
        if edl_errors:
            for err in edl_errors:
                ctx.log(
                    f"master/edl.json: {err}",
                    level="error",
                    stage="edl",
                )
            raise SystemExit(
                f"edl: edl.json failed schema validation ({len(edl_errors)} error(s))"
            )
        from interview_mux.air_order import write_live_edl

        write_live_edl(ctx, edl, source="edl")
        try:
            from interview_mux.gap_vo_gates import gap_framing_enabled
            from interview_mux.opening_orientation import (
                orientation_omitted,
                validate_opening_orientation,
            )

            if gap_framing_enabled(ctx) and isinstance(gap_report, dict):
                active_framing_lines = [
                    line
                    for line in (gap_report.get("interviewer_lines") or [])
                    if isinstance(line, dict) and not line.get("skipped_optional")
                ]
                if active_framing_lines or orientation_omitted(gap_report):
                    opening_errors = validate_opening_orientation(
                        gap_report=gap_report,
                        edl=edl,
                    )
                    if opening_errors:
                        raise RuntimeError(
                            "edl: opening orientation contract failed at stage_done: "
                            + "; ".join(opening_errors)
                        )
        except ImportError:
            pass

    with logged_step("edl/assembly_ledger", ctx=ctx, stage="edl"):
        from interview_mux.assembly_ledger import (
            assert_ledger_no_naked_seams,
            write_assembly_ledger,
        )

        ledger = write_assembly_ledger(ctx, edl=edl)
        if not soft:
            assert_ledger_no_naked_seams(ledger)
        elif ledger.get("naked_seam_count"):
            ctx.log(
                f"assembly_ledger: {ledger.get('naked_seam_count')} naked seam(s) "
                "(NLE soft — operator must repair)",
                level="warning",
                stage="edl",
            )
    try:
        from interview_mux.publishability_boundary import checkpoint_publishability

        checkpoint_publishability(ctx, checkpoint="post_edl")
    except Exception as exc:
        from interview_mux.publishability_boundary import PublishabilityBlocked

        if isinstance(exc, PublishabilityBlocked):
            raise
        ctx.log(
            f"edl: publishability checkpoint skipped: {exc}",
            level="warning",
            stage="edl",
        )
    ctx.mark_done("edl")


def run_mix(ctx: RunContext) -> Path:
    """Flow 1 assembly mix — speech + VO + SDP overlays (canonical stage id)."""
    from interview_mux.air_order import assert_consumer
    from interview_mux.llm_flow_hardening import require_spend_artifacts_complete
    from interview_mux.sound_design import mix

    require_spend_artifacts_complete(ctx, "mix")
    assert_consumer(ctx, "mix")

    try:
        from interview_mux.publishability_boundary import checkpoint_publishability

        checkpoint_publishability(ctx, checkpoint="pre_mix")
    except Exception as exc:
        from interview_mux.publishability_boundary import PublishabilityBlocked

        if isinstance(exc, PublishabilityBlocked):
            raise
        ctx.log(
            f"mix: publishability checkpoint skipped: {exc}",
            level="warning",
            stage="mix",
        )

    try:
        from interview_mux.listen_quality import place_episode_close_cue

        placed = place_episode_close_cue(ctx)
        if placed:
            ctx.log(
                f"mix: placed episode_close cue via {placed}",
                level="info",
                stage="mix",
            )
    except Exception as exc:
        ctx.log(f"mix: episode_close place skipped: {exc}", level="warning", stage="mix")

    # Restore or generate MMAudio QA before mix loud-fail.
    try:
        from interview_mux.delivery_recovery import ensure_mmaudio_qa_before_mix

        qa_state = ensure_mmaudio_qa_before_mix(ctx, run_if_missing=True)
        if not qa_state.get("ok"):
            from interview_mux.stage_resilience import escalate_stage_failure

            escalate_stage_failure(
                ctx,
                "mix",
                failed_invariant="mmaudio_qa_missing",
                evidence=qa_state,
            )
    except Exception:
        pass

    if ctx.artifact_exists("master/assembly_ledger.json"):
        from interview_mux.assembly_ledger import assert_ledger_no_naked_seams

        ledger = ctx.read_json("master/assembly_ledger.json")
        if isinstance(ledger, dict):
            assert_ledger_no_naked_seams(ledger)

    check_edl_qc(ctx, stage="mix", strict=False)

    try:
        from interview_mux.transition_vo import (
            commit_current_transition_wavs,
            current_transition_pairs_missing,
            restamp_edl_transition_source_paths,
        )

        pre_missing = current_transition_pairs_missing(ctx)
        if pre_missing:
            ctx.log(
                "mix: current transition pairs missing WAV — resync before render: "
                + ", ".join(pre_missing[:8]),
                level="warning",
                stage="mix",
            )
            commit_current_transition_wavs(ctx)
            restamp_edl_transition_source_paths(ctx)
    except Exception as exc:
        ctx.log(f"mix: VO pair resync skipped: {exc}", level="warning", stage="mix")

    with logged_step("mix/render", ctx=ctx, stage="mix"):
        out = mix(ctx)
    try:
        from interview_mux.transition_vo import current_transition_pairs_missing, persist_vo_pair_gap

        still = current_transition_pairs_missing(ctx)
        persist_vo_pair_gap(ctx, still, source="mix")
        if still:
            ctx.log(
                "mix: current transition pairs still missing WAV after last-chance: "
                + ", ".join(still[:8]),
                level="error",
                stage="mix",
            )
    except Exception:
        pass
    try:
        from interview_mux.listen_delight import rerun_listen_delight_after_mix

        rerun_listen_delight_after_mix(ctx)
    except Exception as exc:
        ctx.log(f"mix: post-mix listen delight skipped: {exc}", level="warning", stage="mix")
    return out


def run_mux(ctx: RunContext) -> Path:
    """Backward-compatible alias for mix (v1 pipeline stage id)."""
    assembly = run_mix(ctx)
    ctx.mark_done("mux_flow1")
    return assembly


def run_preview(ctx: RunContext) -> Path:
    """Build Flow 1 assembly preview: speech + recorded VO pickup, no SFX."""
    edl = ctx.read_json("master/edl.json")
    source = ctx.read_path("ingest", "normalized.wav")
    work = ctx.path("master", "_preview_clips")
    work.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []

    with logged_step("assembly_preview/render_clips", ctx=ctx, stage="assembly_preview"):
        for i, clip in enumerate(edl.get("clips") or []):
            ctype = clip.get("type")
            out = work / f"clip_{i:04d}.wav"
            if ctype == "speech":
                start = max(0, float(clip.get("source_start_ms", 0)) / 1000.0)
                end = max(start, float(clip.get("source_end_ms", 0)) / 1000.0)
                run_command(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(source),
                        "-ss",
                        str(start),
                        "-to",
                        str(end),
                        "-vn",
                        "-ac",
                        "1",
                        "-ar",
                        "48000",
                        "-c:a",
                        "pcm_s16le",
                        str(out),
                    ],
                    stage="assembly_preview",
                    label=f"ffmpeg speech clip {i}",
                    capture_output=True,
                )
                clip_paths.append(out)
                continue

            if ctype == "silence":
                pad_ms = max(0, int(clip.get("duration_ms") or 0))
                if pad_ms <= 0:
                    continue
                run_command(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        f"anullsrc=r=48000:cl=mono",
                        "-t",
                        f"{pad_ms / 1000.0:.3f}",
                        "-c:a",
                        "pcm_s16le",
                        str(out),
                    ],
                    stage="assembly_preview",
                    label=f"ffmpeg silence clip {i}",
                    capture_output=True,
                )
                clip_paths.append(out)
                continue

            if ctype not in {"vo_pickup", "transition"}:
                continue

            src_rel = clip.get("source_path")
            if not src_rel:
                if ctype == "transition" and not str(clip.get("text") or "").strip():
                    continue
                raise RuntimeError(
                    f"assembly_preview: {ctype} clip {clip.get('line_id') or i} missing source_path"
                )
            vo_src = ctx.read_path(src_rel)
            if not vo_src.is_file():
                raise FileNotFoundError(f"assembly_preview: {ctype} clip missing WAV: {src_rel}")
            run_command(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(vo_src),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "48000",
                    "-c:a",
                    "pcm_s16le",
                    str(out),
                ],
                stage="assembly_preview",
                label=f"ffmpeg {ctype} clip {i}",
                capture_output=True,
            )
            clip_paths.append(out)

    if not clip_paths:
        raise SystemExit(
            "assembly_preview: no renderable speech/VO clips found in edl output."
        )

    from interview_mux.audio_timeline import concat_clips_with_crossfade
    from interview_mux.config import merged_config
    from interview_mux.sound_design import load_audio

    crossfade_ms = int((merged_config().get("mix") or {}).get("crossfade_ms_assembly_preview", 80))
    with logged_step("assembly_preview/concat_export", ctx=ctx, stage="assembly_preview"):
        clips = [load_audio(p) for p in clip_paths]
        preview_audio = concat_clips_with_crossfade(clips, crossfade_ms)
        preview = ctx.path("master", "assembly_preview.wav")
        preview_audio.export(str(preview), format="wav")
    ctx.log(
        f"Assembly preview ready (speech + VO, crossfade_ms={crossfade_ms}, clips={len(clips)}) — listen before MMAudio SFX generation.",
        level="success",
        stage="assembly_preview",
        detail=str(preview),
    )
    ctx.mark_done("assembly_preview")
    return preview
