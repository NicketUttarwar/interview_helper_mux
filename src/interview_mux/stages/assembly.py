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
    return max(0, int(float(proc.stdout.strip()) * 1000))


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
    emitted_text_keys: set[tuple[str, str, str]] | None = None,
) -> list[dict]:
    if not gap_report:
        return []
    out: list[dict] = []
    seen_ids = emitted_line_ids if emitted_line_ids is not None else set()
    seen_text = emitted_text_keys if emitted_text_keys is not None else set()
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
        text_key = (
            str(segment_id),
            str(placement),
            _normalize_vo_text(str(line.get("text") or "")),
        )
        if text_key[2] and text_key in seen_text:
            continue
        if lid:
            seen_ids.add(lid)
        if text_key[2]:
            seen_text.add(text_key)
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
) -> dict:
    """Build Flow 1 EDL: speech order from selection, gap VO placements, transition anchors.

    When ``ideal_cuts`` / ``transcript_words`` are provided, speech clips use
    tightened air bounds (ideal window + complete-thought trim) instead of the
    full coarse segment slab.
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
    missing_transitions: list[str] = []
    air_cfg = listenability_guards_cfg()
    words = [w for w in (transcript_words or []) if isinstance(w, dict)]
    if max_keeper_ms is None:
        try:
            from interview_mux.ideal_cuts import ideal_cuts_cfg

            max_keeper_ms = int(ideal_cuts_cfg().get("max_cut_ms") or 180_000)
        except Exception:
            max_keeper_ms = 180_000

    def _append_air(kind: str, ref_dur: int) -> None:
        nonlocal timeline_ms
        pad = air_pad_ms(ref_dur, kind=kind, cfg=air_cfg)
        if pad <= 0:
            return
        clips.append(
            {
                "type": "silence",
                "air_kind": kind,
                "duration_ms": pad,
                "timeline_start_ms": timeline_ms,
            }
        )
        timeline_ms += pad

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
    emitted_text_keys: set[tuple[str, str, str]] = set()

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
                emitted_text_keys=set(emitted_text_keys),
            )
        )

        before_lines = (
            []
            if skip_before_vo
            else _gap_lines_for_segment(
                gap_report,
                sid,
                "before",
                emitted_line_ids=emitted_line_ids,
                emitted_text_keys=emitted_text_keys,
            )
        )
        # One host turn per seam: if prior clip already left a VO/transition, skip.
        if _last_non_silence_type() in {"vo_pickup", "transition"}:
            before_lines = []

        for line in before_lines:
            vo_path = resolve_vo_path(line) if resolve_vo_path else None
            rel: str | None = None
            dur = 0
            if vo_path is None or not vo_path.is_file():
                delivery = str(line.get("delivery") or "").lower()
                if delivery == "synthesize":
                    missing_vo.append(line.get("line_id") or sid)
                    continue
                missing_vo.append(line.get("line_id") or sid)
            else:
                rel = vo_relpath(vo_path) if vo_relpath else vo_path.as_posix()
                dur = duration_fn(vo_path)

            clip = {
                "type": "vo_pickup",
                "line_id": line.get("line_id"),
                "targets_segment_id": sid,
                "placement": "before",
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
                    "placement": "before",
                    "timeline_start_ms": timeline_ms,
                }
            )
            timeline_ms += dur
            if dur > 0:
                if _is_orientation(line):
                    _append_opening_music_marker(dur)
                else:
                    _append_air("after_vo", dur)

        speech_start = int(seg["start_ms"])
        speech_end = int(seg["end_ms"])
        if ideal_cuts is not None or words:
            speech_start, speech_end = resolve_keeper_air_bounds(
                source_start_ms=speech_start,
                source_end_ms=speech_end,
                cuts_doc=ideal_cuts if isinstance(ideal_cuts, (dict, list)) else None,
                words=words or None,
                segment_id=str(sid),
                max_keep_ms=max_keeper_ms,
            )
        speech_dur = max(0, speech_end - speech_start)
        if clips and str(clips[-1].get("type") or "") == "silence":
            pass
        elif any(c.get("type") == "vo_pickup" for c in clips[-3:]):
            _append_air("before_answer", speech_dur)
        clips.append(
            {
                "segment_id": sid,
                "source_start_ms": speech_start,
                "source_end_ms": speech_end,
                "timeline_start_ms": timeline_ms,
                "duration_ms": speech_dur,
                "type": "speech",
            }
        )
        timeline_ms += speech_dur

        after_lines = _gap_lines_for_segment(
            gap_report,
            sid,
            "after",
            emitted_line_ids=emitted_line_ids,
            emitted_text_keys=emitted_text_keys,
        )
        # Prefer a before-VO layup on the next clip over an after-VO on this one.
        if next_before_vo:
            after_lines = []

        for line in after_lines:
            if _is_orientation(line):
                _append_opening_music_marker(
                    int(line.get("estimated_duration_sec") or 1) * 1000
                )
            vo_path = resolve_vo_path(line) if resolve_vo_path else None
            rel = None
            dur = 0
            if vo_path is None or not vo_path.is_file():
                delivery = str(line.get("delivery") or "").lower()
                if delivery == "synthesize":
                    missing_vo.append(line.get("line_id") or sid)
                    continue
                missing_vo.append(line.get("line_id") or sid)
            else:
                rel = vo_relpath(vo_path) if vo_relpath else vo_path.as_posix()
                dur = duration_fn(vo_path)

            clip = {
                "type": "vo_pickup",
                "line_id": line.get("line_id"),
                "targets_segment_id": sid,
                "placement": "after",
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
                    "placement": "after",
                    "timeline_start_ms": timeline_ms,
                }
            )
            timeline_ms += dur
            if dur > 0:
                _append_air("after_vo", dur)

        if idx + 1 < len(ordered):
            nxt = ordered[idx + 1]
            tr = _transition_after_segment(transitions, sid, nxt)
            if tr:
                from interview_mux.gap_framing import transition_redundant_with_framing

                if transition_redundant_with_framing(gap_report, sid, nxt):
                    tr = None
                elif _last_non_silence_type() == "vo_pickup":
                    tr = None
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
                        "source_path": tr_rel,
                        "duration_ms": tr_dur,
                        "timeline_start_ms": timeline_ms,
                        "script_hash": script_hash(text),
                    }
                )
                timeline_ms += tr_dur
                if tr_dur > 0:
                    _append_air("chapter_hinge", tr_dur)
                else:
                    _append_air("chapter_hinge", speech_dur)

    return {
        "version": 1,
        "ordered_segment_ids": ordered,
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
        },
        "mux_scope": "full_mix",
    }


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
        selection = ctx.read_json("master/selection.json")
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
        transitions = (
            ctx.read_json("master/transitions.json")
            if ctx.artifact_exists("master/transitions.json")
            else {"transitions": []}
        )
        from interview_mux.nle_state import nle_has_operator_edits as _nle_ops
        from interview_mux.order_hash import stamp_order_hash
        from interview_mux.seam_glue import ensure_seam_glue

        ordered = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
        selection = stamp_order_hash(selection)
        ctx.write_json("master/selection.json", selection)

        soft = bool(_nle_ops(nle))
        try:
            meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
            if bool((meta or {}).get("e2e_soft_junction_residuals")):
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
        if soft and not completeness.get("complete"):
            ctx.log(
                f"bridge_completeness soft: "
                f"{completeness.get('missing_count')} missing — shipping",
                level="warning",
                stage="edl",
                detail=completeness.get("missing", [])[:6],
            )

    with logged_step("edl/synthesize_transitions", ctx=ctx, stage="edl"):
        from interview_mux.transition_vo import (
            assert_required_bridge_synth_ok,
            assert_spoken_transitions_audible,
            resolve_transition_wav,
            synthesize_spoken_transitions,
        )

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

    with logged_step("edl/build_edl", ctx=ctx, stage="edl"):
        from interview_mux.order_hash import stamp_order_hash
        from interview_mux.ideal_cuts import load_air_bound_inputs

        ideal_cuts_doc, transcript_words = load_air_bound_inputs(ctx)
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
        )
        edl = stamp_order_hash(edl)
        try:
            from interview_mux.gap_vo_gates import gap_framing_enabled
            from interview_mux.opening_orientation import validate_opening_orientation

            active_framing_lines = [
                line
                for line in ((gap_report or {}).get("interviewer_lines") or [])
                if isinstance(line, dict) and not line.get("skipped_optional")
            ]
            if gap_framing_enabled(ctx) and active_framing_lines:
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
    assert_spoken_transitions_audible(ctx, edl)
    check_edl_qc(ctx, stage="edl", edl=edl, strict=True)
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
        ctx.write_json("master/edl.json", edl)

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
    ctx.mark_done("edl")


def run_mix(ctx: RunContext) -> Path:
    """Flow 1 assembly mix — speech + VO + SDP overlays (canonical stage id)."""
    from interview_mux.llm_flow_hardening import require_spend_artifacts_complete
    from interview_mux.order_hash import order_hashes_match
    from interview_mux.sound_design import mix

    require_spend_artifacts_complete(ctx, "mix")

    if ctx.artifact_exists("master/selection.json") and ctx.artifact_exists("master/edl.json"):
        sel = ctx.read_json("master/selection.json")
        edl = ctx.read_json("master/edl.json")
        if isinstance(sel, dict) and isinstance(edl, dict) and not order_hashes_match(sel, edl):
            raise SystemExit(
                "mix: selection ordered_segment_ids drifted from edl — "
                "re-run edl (and remaster) before mix"
            )
    if ctx.artifact_exists("master/assembly_ledger.json"):
        from interview_mux.assembly_ledger import assert_ledger_no_naked_seams

        ledger = ctx.read_json("master/assembly_ledger.json")
        if isinstance(ledger, dict):
            assert_ledger_no_naked_seams(ledger)

    check_edl_qc(ctx, stage="mix", strict=False)
    with logged_step("mix/render", ctx=ctx, stage="mix"):
        return mix(ctx)


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
