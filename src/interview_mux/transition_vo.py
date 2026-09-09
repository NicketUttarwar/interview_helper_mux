"""Synthesize spoken chapter-transition bridges via the same VO path as gap lines."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.creative_delivery import creative_delivery_required
from interview_mux.run_context import RunContext


def _transition_line_id(after_id: str, before_id: str) -> str:
    return f"tr_{after_id}_{before_id}"


def _pair_key(after_id: str, before_id: str) -> str:
    return f"{after_id}->{before_id}"


def _parse_pair_key(key: str) -> tuple[str, str] | None:
    raw = str(key or "").strip()
    if "->" not in raw:
        return None
    after_id, before_id = raw.split("->", 1)
    after_id = after_id.strip()
    before_id = before_id.strip()
    if not after_id or not before_id:
        return None
    return after_id, before_id


def transition_wav_path(ctx: RunContext, after_id: str, before_id: str) -> Path:
    out_dir = ctx.path("master", "transitions")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{_transition_line_id(after_id, before_id)}.wav"


def _transition_wav_usable(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 1000:
        return False
    try:
        import wave

        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate() or 1
            frames = wf.getnframes()
            return (1000 * frames / rate) > 0
    except Exception:
        return path.stat().st_size > 1000


def current_pair_wav_usable(
    ctx: RunContext, after_id: str, before_id: str
) -> Path | None:
    """On-disk WAV bytes that can play (existence only — no script_hash check).

    Prefer ``resolve_transition_wav`` for completeness, incompleteness, reseat, and
    mix last-chance. This helper remains for low-level "file exists" probes during
    staging when audit may not be written yet.
    """
    if not after_id or not before_id:
        return None
    path = transition_wav_path(ctx, after_id, before_id)
    if _transition_wav_usable(path):
        return path
    committed = ctx.final_path(
        "master", "transitions", f"{_transition_line_id(after_id, before_id)}.wav"
    )
    if committed != path and _transition_wav_usable(committed):
        return committed
    return None


def spoken_transition_pairs(ctx: RunContext) -> list[tuple[str, str]]:
    """Current ``transitions.json`` pairs that have spoken text."""
    if not ctx.artifact_exists("master/transitions.json"):
        return []
    try:
        doc = ctx.read_json("master/transitions.json")
    except Exception:
        return []
    if not isinstance(doc, dict):
        return []
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in doc.get("transitions") or []:
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            continue
        after_id = str(item.get("after_segment_id") or "")
        before_id = str(item.get("before_segment_id") or "")
        if not after_id or not before_id:
            continue
        key = (after_id, before_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def persist_vo_pair_gap(
    ctx: RunContext,
    missing: list[str],
    *,
    source: str,
    extra: dict[str, Any] | None = None,
    skip_handoff: bool = True,
    stage_key: str | None = None,
) -> None:
    """Durable still_missing_pairs so remap/junction/mix gaps are visible without logs."""
    from datetime import datetime, timezone

    rel = "mastering/vo_synthesize.json"
    prev: dict[str, Any] = {}
    if ctx.artifact_exists(rel):
        try:
            raw = ctx.read_json(rel)
            if isinstance(raw, dict):
                prev = raw
        except Exception:
            prev = {}
    doc = dict(prev)
    try:
        doc["version"] = int(doc.get("version") or 1)
    except (TypeError, ValueError):
        doc["version"] = 1
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    doc["still_missing_pairs"] = [str(m) for m in missing]
    doc["last_source"] = source
    if extra:
        doc.update(extra)
    try:
        ctx.write_json(rel, doc, skip_handoff=skip_handoff, stage_key=stage_key)
    except Exception:
        pass


def resolve_transition_wav(
    ctx: RunContext, after_id: str, before_id: str
) -> Path | None:
    path = current_pair_wav_usable(ctx, after_id, before_id)
    if path is None or not ctx.artifact_exists("master/transitions.json"):
        return None
    doc = ctx.read_json("master/transitions.json")
    item = next(
        (
            row
            for row in ((doc or {}).get("transitions") or [])
            if isinstance(row, dict)
            and str(row.get("after_segment_id") or "") == str(after_id)
            and str(row.get("before_segment_id") or "") == str(before_id)
        ),
        None,
    )
    if not isinstance(item, dict) or not str(item.get("text") or "").strip():
        return None
    by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        by_id = {
            str(row.get("segment_id")): row
            for row in ((manifest or {}).get("segments") or [])
            if isinstance(row, dict) and row.get("segment_id")
        }
    from interview_mux.spoken_copy_guard import enrich_evidence_from_run

    evidence = enrich_evidence_from_run(
        ctx,
        {
            "before_excerpt": (by_id.get(after_id) or {}).get("text"),
            "after_excerpt": (by_id.get(before_id) or {}).get("text"),
            "before_topic": (by_id.get(after_id) or {}).get("topic"),
            "after_topic": (by_id.get(before_id) or {}).get("topic"),
            "source_gap_ms": item.get("source_gap_ms"),
            "strict_grounding": True,
        },
    )
    line = {
        "line_id": _transition_line_id(after_id, before_id),
        "text": str(item.get("text") or ""),
        "targets_segment_id": after_id,
        "placement": "after",
        "after_segment_id": after_id,
        "before_segment_id": before_id,
        **evidence,
    }
    from interview_mux.vo_synthesis_audit import (
        synthesis_entry_for_line,
        synthesis_entry_matches_line,
    )
    from interview_mux.spoken_copy_guard import script_hash

    matches, _reason = synthesis_entry_matches_line(ctx, line)
    if matches:
        return path
    # Context hash drifts when evidence enrichment / adjacent text changes
    # without rewriting the spoken line. Accept script-matched WAVs on disk.
    entry = synthesis_entry_for_line(ctx, str(line.get("line_id") or ""))
    if (
        entry
        and _transition_wav_usable(path)
        and str(entry.get("script_hash") or "")
        == script_hash(str(item.get("text") or ""))
    ):
        return path
    return None


def _purge_transition_pair_wav(ctx: RunContext, after_id: str, before_id: str) -> int:
    """Delete on-disk transition WAV + synthesis audit for this pair."""
    removed = 0
    lid = _transition_line_id(after_id, before_id)
    for path in (
        transition_wav_path(ctx, after_id, before_id),
        ctx.final_path("master", "transitions", f"{lid}.wav"),
    ):
        if path.is_file():
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    try:
        from interview_mux.vo_synthesis_audit import invalidate_synthesis_entries

        invalidate_synthesis_entries(ctx, [lid])
    except Exception:
        pass
    return removed


def transition_spoken_texts(doc: dict[str, Any] | None) -> dict[str, str]:
    """Map ``after->before`` → spoken text from a transitions document."""
    out: dict[str, str] = {}
    if not isinstance(doc, dict):
        return out
    for item in doc.get("transitions") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        after_id = str(item.get("after_segment_id") or "").strip()
        before_id = str(item.get("before_segment_id") or "").strip()
        if not text or not after_id or not before_id:
            continue
        out[f"{after_id}->{before_id}"] = text
    return out


def maybe_propagate_transitions_spoken_text_change(
    ctx: RunContext,
    *,
    prior_doc: dict[str, Any] | None,
    new_doc: dict[str, Any],
    stage: str | None = None,
) -> dict[str, Any]:
    """Cascade when spoken transition bridge text changes.

    Purge stale pair WAVs/audit and unmark vo_synthesize / edl / mix so reseat
    can regenerate bridges before master finalize.
    """
    if getattr(ctx, "_spoken_text_cascade_depth", 0):
        return {"changed": [], "purged": [], "unmarked": [], "skipped": "reentrant"}
    if not isinstance(new_doc, dict):
        return {"changed": [], "purged": [], "unmarked": []}
    prior = transition_spoken_texts(prior_doc)
    new = transition_spoken_texts(new_doc)
    changed_keys: list[str] = []
    for key, text in new.items():
        if prior.get(key) != text:
            changed_keys.append(key)
    for key in prior:
        if key not in new:
            changed_keys.append(key)
    changed_keys = sorted(set(changed_keys))
    if not changed_keys:
        return {"changed": [], "purged": [], "unmarked": []}

    stale: list[tuple[str, str]] = []
    for key in changed_keys:
        parsed = _parse_pair_key(key)
        if not parsed:
            continue
        after_id, before_id = parsed
        if key not in new:
            # Removed pair — drop orphan audio.
            if current_pair_wav_usable(ctx, after_id, before_id) is not None:
                stale.append(parsed)
            continue
        # Spoken text changed for this pair — purge regardless of existence.
        stale.append(parsed)

    if not stale and not changed_keys:
        return {"changed": [], "purged": [], "unmarked": []}

    setattr(ctx, "_spoken_text_cascade_depth", 1)
    try:
        purged: list[str] = []
        for after_id, before_id in stale:
            _purge_transition_pair_wav(ctx, after_id, before_id)
            purged.append(f"{after_id}->{before_id}")
        unmarked: list[str] = []
        try:
            from interview_mux.vo_synthesis_audit import (
                unmark_transition_spoken_text_cascade_stages,
            )

            # Only unmark when we actually invalidated audio or text changed on a
            # pair that already had consumers done.
            if purged or any(ctx.is_done(s) for s in ("vo_synthesize", "edl", "mix")):
                unmarked = unmark_transition_spoken_text_cascade_stages(ctx)
        except Exception:
            unmarked = []
        if purged or unmarked:
            ctx.log(
                "Transition spoken text cascade: "
                f"purged={len(purged)} unmarked={unmarked[:6]}",
                level="warning",
                stage=stage or "transitions_write",
                detail={"purged": purged[:24], "unmarked": unmarked},
            )
        return {"changed": changed_keys, "purged": purged, "unmarked": unmarked}
    finally:
        setattr(ctx, "_spoken_text_cascade_depth", 0)


def resync_spoken_transitions(ctx: RunContext, *, fail_closed: bool = False) -> list[str]:
    """Re-synth spoken transitions that resolve as missing/stale. Once per call.

    Missing files after the one try are returned in the note list. Raise only when
    ``fail_closed`` is True — mix last-chance is the net, not an EDL crash.
    """
    if not ctx.artifact_exists("master/transitions.json"):
        return []
    doc = ctx.read_json("master/transitions.json")
    if not isinstance(doc, dict):
        return []
    needed: list[tuple[str, str]] = []
    for item in doc.get("transitions") or []:
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            continue
        after_id = str(item.get("after_segment_id") or "")
        before_id = str(item.get("before_segment_id") or "")
        if not after_id or not before_id:
            continue
        if resolve_transition_wav(ctx, after_id, before_id) is None:
            needed.append((after_id, before_id))
    if not needed:
        return []
    # Drop stale bytes so Chatterbox cannot skip-fresh on existence alone.
    for after_id, before_id in needed:
        _purge_transition_pair_wav(ctx, after_id, before_id)
    synthesize_spoken_transitions(ctx, pairs=set(needed))
    still_bad: list[str] = []
    notes: list[str] = []
    for after_id, before_id in needed:
        key = f"{after_id}->{before_id}"
        notes.append(key)
        if resolve_transition_wav(ctx, after_id, before_id) is None:
            still_bad.append(key)
    if still_bad:
        msg = (
            "edl: spoken transitions still unresolved after resync: "
            + ", ".join(still_bad[:8])
        )
        ctx.log(msg, level="warning", stage="edl")
        if fail_closed:
            raise RuntimeError(msg)
        notes.extend(f"missing:{k}" for k in still_bad)
    return notes


def synthesize_spoken_transitions(
    ctx: RunContext,
    *,
    pairs: set[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Generate WAVs for transitions that have spoken text. Returns result rows."""
    if not ctx.artifact_exists("master/transitions.json"):
        return []
    doc = ctx.read_json("master/transitions.json")
    if not isinstance(doc, dict):
        return []
    items = doc.get("transitions") or []
    if not isinstance(items, list):
        return []

    from interview_mux.s2s_runner import synthesize_line
    from interview_mux.source_topology import pickup_eligible_speaker_id
    from interview_mux.spoken_copy_guard import assert_guarded_spoken_copy
    from interview_mux.vo_synthesis_audit import synthesis_entry_matches_line

    # Prefer episode VO lock, then speaker_delivery_plan clone, then pickup.
    speaker_id = ""
    try:
        from interview_mux.speaker_delivery_plan import episode_vo_identity

        speaker_id = str((episode_vo_identity(ctx) or {}).get("speaker_id") or "")
    except Exception:
        speaker_id = ""
    if not speaker_id and ctx.artifact_exists("understanding/speaker_delivery_plan.json"):
        try:
            sdp = ctx.read_json("understanding/speaker_delivery_plan.json")
            if isinstance(sdp, dict):
                speaker_id = str(sdp.get("clone_speaker_id") or "")
        except Exception:
            speaker_id = ""
    if not speaker_id:
        speaker_id = pickup_eligible_speaker_id(ctx) or ""
    by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        by_id = {
            str(row.get("segment_id")): row
            for row in ((manifest or {}).get("segments") or [])
            if isinstance(row, dict) and row.get("segment_id")
        }
    results: list[dict[str, Any]] = []
    writeback = False
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        after_id = str(item.get("after_segment_id") or "")
        before_id = str(item.get("before_segment_id") or "")
        if not after_id or not before_id:
            continue
        if pairs is not None and (after_id, before_id) not in pairs:
            continue
        from interview_mux.spoken_copy_guard import enrich_evidence_from_run

        evidence = enrich_evidence_from_run(
            ctx,
            {
                "before_excerpt": (by_id.get(after_id) or {}).get("text"),
                "after_excerpt": (by_id.get(before_id) or {}).get("text"),
                "before_topic": (by_id.get(after_id) or {}).get("topic"),
                "after_topic": (by_id.get(before_id) or {}).get("topic"),
                "source_gap_ms": item.get("source_gap_ms"),
                "strict_grounding": True,
            },
        )
        try:
            guarded = assert_guarded_spoken_copy(
                text,
                evidence=evidence,
                purpose=f"transition[{after_id}->{before_id}]",
                ctx=ctx,
            )
        except ValueError:
            from interview_mux.seam_glue import (
                bridge_guard_evidence,
                default_bridge_text,
                enrich_bridge_pair_excerpts,
            )

            pair = enrich_bridge_pair_excerpts(
                {
                    "after_segment_id": after_id,
                    "before_segment_id": before_id,
                    "source_gap_ms": item.get("source_gap_ms"),
                },
                by_id,
            )
            alt = str(default_bridge_text(pair) or "").strip()
            if not alt:
                raise ValueError(
                    f"transition text blocked before synthesis "
                    f"({after_id}->{before_id}): ungrounded seam"
                )
            guarded = assert_guarded_spoken_copy(
                alt,
                evidence=bridge_guard_evidence(pair),
                purpose=f"transition[{after_id}->{before_id}]",
                ctx=ctx,
            )
        text = str(guarded["text"])
        if text != str(item.get("text") or "").strip():
            item["text"] = text
            item["spoken_copy_guard"] = {
                "action": guarded.get("action"),
                "script_hash": guarded.get("script_hash"),
                "context_hash": guarded.get("context_hash"),
            }
            writeback = True
        out = transition_wav_path(ctx, after_id, before_id)
        line = {
            "line_id": _transition_line_id(after_id, before_id),
            "text": text,
            "delivery": "synthesize",
            "targets_segment_id": after_id,
            "placement": "after",
            "after_segment_id": after_id,
            "before_segment_id": before_id,
            "voice_speaker_id": speaker_id or item.get("voice_speaker_id"),
            "suggested_tone": item.get("tone") or "bridge",
            **evidence,
        }
        try:
            from interview_mux.speaker_delivery_plan import stamp_episode_vo_identity

            line = stamp_episode_vo_identity(ctx, line)
            item["voice_speaker_id"] = line.get("voice_speaker_id") or speaker_id
            if line.get("vo_shape"):
                item["vo_shape"] = line.get("vo_shape")
                writeback = True
        except Exception:
            pass
        audit_match, audit_reason = synthesis_entry_matches_line(ctx, line)
        if audit_match:
            # Pending/re-synth can leave committed transition bytes behind the
            # audit row. Prefer the sha-bound take and seat it at ``out`` so we
            # do not thrash-regenerate every pass (same class as G1 seated VO).
            try:
                from interview_mux.vo_synthesis_audit import (
                    _audited_wav_path,
                    synthesis_entry_for_line,
                    wav_content_sha256,
                )

                entry = synthesis_entry_for_line(ctx, str(line.get("line_id") or ""))
                audited = (
                    _audited_wav_path(ctx, entry, line)
                    if isinstance(entry, dict)
                    else None
                )
                bound = str((entry or {}).get("wav_sha256") or "").strip()
                if (
                    audited is not None
                    and audited.is_file()
                    and bound
                    and (
                        not out.is_file()
                        or wav_content_sha256(out) != bound
                        or audited.resolve() != out.resolve()
                    )
                ):
                    out.parent.mkdir(parents=True, exist_ok=True)
                    if audited.resolve() != out.resolve():
                        import shutil

                        shutil.copy2(audited, out)
            except Exception as exc:
                ctx.log(
                    f"transition seat audited take skipped {after_id}→{before_id}: {exc}",
                    level="warning",
                    stage="edl",
                )
        if out.is_file() and _transition_wav_usable(out) and audit_match:
            results.append(
                {
                    "after_segment_id": after_id,
                    "before_segment_id": before_id,
                    "path": out.as_posix(),
                    "skipped": True,
                    "script_hash_match": True,
                }
            )
            continue
        if out.is_file() and not audit_match:
            ctx.log(
                f"Transition WAV stale ({audit_reason}); regenerating {after_id}→{before_id}",
                level="warning",
                stage="edl",
            )
        last_err: Exception | None = None
        wav = None
        for attempt in range(2):
            try:
                wav = synthesize_line(ctx, line, mode="synthesize", dest_dir=out.parent)
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                ctx.log(
                    f"Transition synth attempt {attempt + 1} failed "
                    f"{after_id}→{before_id}: {exc}",
                    level="warning" if attempt == 0 else "error",
                    stage="edl",
                )
        if last_err is not None or wav is None:
            results.append(
                {
                    "after_segment_id": after_id,
                    "before_segment_id": before_id,
                    "ok": False,
                    "error": str(last_err)[:300] if last_err else "no_wav",
                    "required": True,
                }
            )
            continue
        # synthesize_line writes under vo_pickup/synthesized/{line_id}.wav —
        # copy/rename into master/transitions when needed.
        if wav.resolve() != out.resolve():
            try:
                out.write_bytes(wav.read_bytes())
            except OSError as exc:
                results.append(
                    {
                        "after_segment_id": after_id,
                        "before_segment_id": before_id,
                        "ok": False,
                        "error": f"copy_failed:{exc}",
                        "required": True,
                    }
                )
                continue
        if not _transition_wav_usable(out):
            results.append(
                {
                    "after_segment_id": after_id,
                    "before_segment_id": before_id,
                    "ok": False,
                    "error": "unusable_wav",
                    "required": True,
                }
            )
            continue
        results.append(
            {
                "after_segment_id": after_id,
                "before_segment_id": before_id,
                "path": out.as_posix(),
                "ok": True,
            }
        )
        ctx.log(
            f"Synthesized transition {after_id}→{before_id}",
            level="info",
            stage="edl",
            detail={"event": "transition_synth", "path": out.as_posix()},
        )
        try:
            from interview_mux.asset_transcripts import write_transition_sidecar_for_item

            write_transition_sidecar_for_item(ctx, item, wav_path=out)
        except Exception:
            pass
    if writeback:
        persist_transitions_doc(ctx, doc, stage_key="edl")
    return results


def assert_required_bridge_synth_ok(
    ctx: RunContext, synth_rows: list[dict[str, Any]]
) -> None:
    """Fail-closed when a required reorder-bridge transition synth failed twice."""
    from interview_mux.bridge_completeness import required_bridge_keys

    bridges = None
    if ctx.artifact_exists("understanding/reorder_bridges.json"):
        bridges = ctx.read_json("understanding/reorder_bridges.json")
    required = required_bridge_keys(bridges if isinstance(bridges, dict) else None)
    # Also treat any spoken transition with text as required once listed
    failed = [
        r
        for r in synth_rows
        if isinstance(r, dict) and r.get("ok") is False
    ]
    blocking: list[str] = []
    for row in failed:
        a = str(row.get("after_segment_id") or "")
        b = str(row.get("before_segment_id") or "")
        if (a, b) in required or row.get("required"):
            blocking.append(f"{a}->{b}")
    if blocking:
        raise SystemExit(
            "transition synth fail-closed after retry for required bridge(s): "
            + ", ".join(blocking[:8])
        )


def assert_spoken_transitions_audible(ctx: RunContext, edl: dict[str, Any]) -> None:
    """Block when creative delivery is on and spoken transition text has duration_ms==0."""
    if not creative_delivery_required():
        # Still block when gap framing / voice clone is active on this run.
        from interview_mux.gap_vo_gates import gap_framing_enabled, resolve_gap_vo_delivery

        if not gap_framing_enabled(ctx):
            return
        if resolve_gap_vo_delivery(ctx) not in {"chatterbox", "synthesize", "voice_clone"}:
            return

    bad: list[str] = []
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict) or clip.get("type") != "transition":
            continue
        text = str(clip.get("text") or "").strip()
        if not text:
            continue
        dur = int(clip.get("duration_ms") or 0)
        src = clip.get("source_path")
        if not src:
            # Explicit empty seat — mix last-chance or silence, not an EDL crash.
            continue
        if dur <= 0:
            after = clip.get("after_segment_id")
            before = clip.get("before_segment_id")
            bad.append(f"{after}->{before}")
    if bad:
        raise SystemExit(
            "edl: spoken transitions missing audio (duration_ms==0 or no source_path): "
            + ", ".join(bad[:8])
        )


def lint_edl_vo_source_paths(ctx: RunContext, edl: dict[str, Any] | None) -> dict[str, Any]:
    """Unset source_path on clips whose file is not on disk. Write-path contract."""
    from interview_mux.edl_source_contract import lint_edl_vo_source_paths as _lint

    return _lint(ctx, edl)


def seated_vo_paths_missing(ctx: RunContext) -> list[str]:
    """Relative source_paths seated on the current EDL whose files are missing."""
    from interview_mux.edl_source_contract import EDL_REL, edl_source_path_ghosts

    if not ctx.artifact_exists(EDL_REL):
        return []
    try:
        edl = ctx.read_json(EDL_REL)
    except Exception:
        return []
    return [
        g
        for g in edl_source_path_ghosts(ctx, edl if isinstance(edl, dict) else None)
        if not g.endswith(":empty")
    ]


def _seated_script_hashes(edl: dict[str, Any] | None, *, skip: dict[str, Any] | None = None) -> set[str]:
    from interview_mux.spoken_copy_guard import script_hash

    out: set[str] = set()
    skip_id = id(skip) if skip is not None else None
    for clip in (edl or {}).get("clips") or []:
        if not isinstance(clip, dict):
            continue
        if skip_id is not None and id(clip) == skip_id:
            continue
        if str(clip.get("type") or "") not in {"vo_pickup", "transition"}:
            continue
        text = str(clip.get("text") or "").strip()
        if text:
            out.add(script_hash(text))
    return out


def last_chance_synth_missing_clip(
    ctx: RunContext,
    clip: dict[str, Any],
    *,
    edl: dict[str, Any] | None = None,
    attempted: set[str] | None = None,
) -> Path | None:
    """Generate once for a seated clip whose WAV is missing. Never reuse another pair's file."""
    from interview_mux.config import merged_config
    from interview_mux.spoken_copy_guard import script_hash
    from interview_mux.vo_speech_qa import vo_passes_speech_qa

    mix_cfg = merged_config().get("mix") or {}
    if mix_cfg.get("missing_vo_retry_once", True) is False:
        return None
    ctype = str(clip.get("type") or "")
    if ctype == "transition":
        after_id = str(clip.get("after_segment_id") or "")
        before_id = str(clip.get("before_segment_id") or "")
        key = f"tr:{after_id}->{before_id}"
        if not after_id or not before_id:
            return None
        if attempted is not None:
            if key in attempted:
                return None
            attempted.add(key)
        existing = resolve_transition_wav(ctx, after_id, before_id)
        if existing is None:
            _purge_transition_pair_wav(ctx, after_id, before_id)
            synthesize_spoken_transitions(ctx, pairs={(after_id, before_id)})
            path = resolve_transition_wav(ctx, after_id, before_id)
        else:
            path = existing
        if path is None:
            return None
        text = str(clip.get("text") or "").strip()
        if not vo_passes_speech_qa(path, cfg=None) and text:
            # Speech QA may be disabled; still require a usable file.
            if not _transition_wav_usable(path):
                return None
        others = _seated_script_hashes(edl, skip=clip)
        if text and script_hash(text) in others:
            ctx.log(
                f"mix: last-chance VO rejected as duplicate seated line ({after_id}->{before_id})",
                level="warning",
                stage="mix",
            )
            return None
        return path
    if ctype == "vo_pickup":
        line_id = str(clip.get("line_id") or "").strip()
        text = str(clip.get("text") or "").strip()
        if not line_id or not text:
            return None
        key = f"vo:{line_id}"
        if attempted is not None:
            if key in attempted:
                return None
            attempted.add(key)
        dest_dir = ctx.path("vo_pickup", "synthesized")
        dest_dir.mkdir(parents=True, exist_ok=True)
        line = dict(clip)
        line["line_id"] = line_id
        line["text"] = text
        line["delivery"] = "synthesize"
        try:
            from interview_mux.s2s_runner import synthesize_line

            wav = synthesize_line(ctx, line, mode="synthesize", dest_dir=dest_dir)
        except Exception as exc:
            ctx.log(
                f"mix: last-chance vo_pickup synth failed ({line_id}): {exc}",
                level="warning",
                stage="mix",
            )
            return None
        if wav is None or not wav.is_file():
            return None
        others = _seated_script_hashes(edl, skip=clip)
        if script_hash(text) in others:
            return None
        if not vo_passes_speech_qa(wav):
            if wav.stat().st_size <= 1000:
                return None
        return wav
    return None


def commit_current_transition_wavs(ctx: RunContext) -> list[str]:
    """Resync current pairs, promote staged WAVs, return still-missing keys.

    Persist runs in ``finally`` so remap/junction log-and-continue cannot hide a
    raised synth. On exception, measure holes from disk — do not persist ``[]``.
    """
    still: list[str] = []
    try:
        ensure_pre_mix_transition_integrity(ctx, synthesize=True)
        notes = resync_spoken_transitions(ctx, fail_closed=False)
        try:
            from interview_mux.write_staging import promote_staged_side_effects

            promote_staged_side_effects(ctx, ("master/transitions/",))
        except Exception:
            pass
        try:
            from interview_mux.vo_synthesis_audit import canonicalize_synthesis_out_wav_paths

            canonicalize_synthesis_out_wav_paths(ctx)
        except Exception:
            pass
        restamp_edl_transition_source_paths(ctx)
        still = [n[len("missing:") :] for n in notes if str(n).startswith("missing:")]
        return still
    finally:
        persist_vo_pair_gap(
            ctx,
            still or current_transition_pairs_missing(ctx),
            source="commit",
        )


def current_transition_pairs_missing(ctx: RunContext) -> list[str]:
    """Spoken current pairs in ``master/transitions.json`` with no hash-fresh WAV.

    Completeness requires ``resolve_transition_wav`` (script_hash match), not mere
    file existence — rewritten bridge text must re-synth before master finalize.
    """
    missing: list[str] = []
    for after_id, before_id in spoken_transition_pairs(ctx):
        if resolve_transition_wav(ctx, after_id, before_id) is None:
            missing.append(f"{after_id}->{before_id}")
    return missing


PAIR_FREEZE_REL = "master/transitions_pair_freeze.json"
DEFERRED_PAIRS_REL = "master/deferred_transition_pairs.json"


def read_transitions_pair_freeze(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(PAIR_FREEZE_REL):
        return None
    try:
        doc = ctx.read_json(PAIR_FREEZE_REL)
    except Exception:
        return None
    return doc if isinstance(doc, dict) else None


def frozen_transition_pair_keys(ctx: RunContext) -> set[str]:
    doc = read_transitions_pair_freeze(ctx)
    if not doc:
        return set()
    return {str(x) for x in (doc.get("pairs") or []) if x}


def stamp_transitions_pair_freeze(ctx: RunContext, *, generation: int | None = None) -> dict[str, Any]:
    """Freeze the spoken pair set on first successful EDL / green G1+transitions write.

    Later selection/EDL deltas that add pairs go to deferred_transition_pairs —
    synth only in mix last-chance, never unmark full vo_synthesize.
    """
    existing = read_transitions_pair_freeze(ctx)
    if existing and existing.get("pairs"):
        # Refresh deferred bucket from current spoken pairs vs freeze.
        _sync_deferred_transition_pairs(ctx)
        return existing
    pairs = [_pair_key(a, b) for a, b in spoken_transition_pairs(ctx)]
    gen = generation
    if gen is None:
        try:
            from interview_mux.air_order import generation as air_generation

            gen = int(air_generation(ctx) or 0)
        except Exception:
            gen = 0
    doc: dict[str, Any] = {
        "version": 1,
        "generation": gen,
        "pairs": sorted(set(pairs)),
        "stamped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    ctx.write_json(PAIR_FREEZE_REL, doc, skip_handoff=True)
    _sync_deferred_transition_pairs(ctx)
    return doc


def clear_transitions_pair_freeze(ctx: RunContext) -> bool:
    """Drop pair freeze (+ deferred) after order/transitions stale so vo incompleteness is honest."""
    removed = False
    for rel in (PAIR_FREEZE_REL, DEFERRED_PAIRS_REL):
        path = ctx.final_path(*rel.split("/"))
        if path.is_file():
            path.unlink(missing_ok=True)
            removed = True
    return removed


def _sync_deferred_transition_pairs(ctx: RunContext) -> list[str]:
    frozen = frozen_transition_pair_keys(ctx)
    if not frozen:
        return []
    current = {_pair_key(a, b) for a, b in spoken_transition_pairs(ctx)}
    deferred = sorted(current - frozen)
    ctx.write_json(
        DEFERRED_PAIRS_REL,
        {
            "version": 1,
            "deferred_pairs": deferred,
            "frozen_count": len(frozen),
            "current_count": len(current),
        },
        skip_handoff=True,
    )
    return deferred


def deferred_transition_pairs(ctx: RunContext) -> list[tuple[str, str]]:
    """Spoken pairs added after the freeze — mix last-chance only."""
    _sync_deferred_transition_pairs(ctx)
    if not ctx.artifact_exists(DEFERRED_PAIRS_REL):
        return []
    try:
        doc = ctx.read_json(DEFERRED_PAIRS_REL)
    except Exception:
        return []
    if not isinstance(doc, dict):
        return []
    out: list[tuple[str, str]] = []
    for key in doc.get("deferred_pairs") or []:
        parsed = _parse_pair_key(str(key))
        if parsed:
            out.append(parsed)
    return out


def vo_synthesize_pair_incompleteness(ctx: RunContext) -> str | None:
    """Missing transition-pair WAVs that should keep vo_synthesize incomplete.

    When a freeze exists and G1 is green, deferred (post-freeze) pairs are ignored
    here — mix last-chance still synths them via ``current_transition_pairs_missing``.
    """
    missing = current_transition_pairs_missing(ctx)
    if not missing:
        return None
    freeze = read_transitions_pair_freeze(ctx)
    if not freeze:
        return f"current transition pairs missing WAV: {', '.join(missing[:4])}"
    try:
        from interview_mux.gates import check_g1_vo, g1_vo_was_skipped_optional

        g1_green = g1_vo_was_skipped_optional(ctx) or not check_g1_vo(ctx)
    except Exception:
        g1_green = False
    if not g1_green:
        return f"current transition pairs missing WAV: {', '.join(missing[:4])}"
    frozen = frozen_transition_pair_keys(ctx)
    frozen_missing = [m for m in missing if m in frozen]
    if frozen_missing:
        return (
            "current transition pairs missing WAV: "
            + ", ".join(frozen_missing[:4])
        )
    # Deferred-only holes: do not flip vo_synthesize incompleteness.
    _sync_deferred_transition_pairs(ctx)
    return None


def _transition_source_rel(ctx: RunContext, path: Path) -> str:
    try:
        rel = path.relative_to(ctx.run_dir).as_posix()
    except ValueError:
        return f"master/transitions/{path.name}"
    prefix = ".pending_writes/"
    if rel.startswith(prefix):
        rest = rel[len(prefix) :]
        if "/" in rest:
            rel = rest.split("/", 1)[1]
    return rel


def restamp_edl_transition_source_paths(ctx: RunContext) -> bool:
    """Set EDL transition ``source_path`` from current-pair WAVs; unset if missing."""
    if not ctx.artifact_exists("master/edl.json"):
        return False
    try:
        edl = ctx.read_json("master/edl.json")
    except Exception:
        return False
    if not isinstance(edl, dict):
        return False
    clips: list[Any] = []
    changed = False
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict) or str(clip.get("type") or "") != "transition":
            clips.append(clip)
            continue
        after_id = str(clip.get("after_segment_id") or "")
        before_id = str(clip.get("before_segment_id") or "")
        wav = (
            resolve_transition_wav(ctx, after_id, before_id)
            if after_id and before_id
            else None
        )
        row = dict(clip)
        if wav is not None and wav.is_file():
            rel = _transition_source_rel(ctx, wav)
            if row.get("source_path") != rel:
                row["source_path"] = rel
                changed = True
            try:
                import wave

                with wave.open(str(wav), "rb") as handle:
                    rate = handle.getframerate() or 1
                    frames = handle.getnframes()
                    dur = int(1000 * frames / rate)
                if int(row.get("duration_ms") or 0) != dur and dur > 0:
                    row["duration_ms"] = dur
                    changed = True
            except Exception:
                pass
        elif row.get("source_path"):
            row.pop("source_path", None)
            row["duration_ms"] = 0
            changed = True
        clips.append(row)
    if not changed:
        return False
    out = dict(edl)
    out["clips"] = clips
    from interview_mux.air_order import write_live_edl

    write_live_edl(ctx, out, source="transition_vo")
    return True


def _justified_skip_before_ids(ctx: RunContext) -> set[str]:
    skip: set[str] = set()
    try:
        from interview_mux.nugget_layup import (
            PLAN_REL,
            is_justified_skip_row,
            nugget_layup_enabled,
        )

        if nugget_layup_enabled() and ctx.artifact_exists(PLAN_REL):
            plan = ctx.read_json(PLAN_REL)
            if isinstance(plan, dict):
                for row in plan.get("layups") or []:
                    if not isinstance(row, dict) or not row.get("skip"):
                        continue
                    tid = str(row.get("target_segment_id") or "").strip()
                    if tid and is_justified_skip_row(row, soft_migrate=True):
                        skip.add(tid)
    except Exception:
        pass
    try:
        from interview_mux.air_script import native_handoff_segment_ids
        from interview_mux.mastering_plan_loader import load_plan_raw

        skip |= native_handoff_segment_ids(load_plan_raw(ctx))
    except Exception:
        pass
    return skip


def _selection_ordered_ids(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return []
    try:
        sel = ctx.read_json("master/selection.json")
    except Exception:
        return []
    if not isinstance(sel, dict):
        return []
    return [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]


def _segments_by_id(ctx: RunContext) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    if not ctx.artifact_exists("segments/manifest.json"):
        return by_id
    try:
        manifest = ctx.read_json("segments/manifest.json")
    except Exception:
        return by_id
    for row in ((manifest or {}).get("segments") or []):
        if isinstance(row, dict) and row.get("segment_id"):
            by_id[str(row.get("segment_id"))] = row
    return by_id


def adjacency_required_transition_pairs(
    ctx: RunContext,
    *,
    transitions_doc: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    """Selection adjacencies that still demand spoken transition glue (not waived)."""
    ordered = _selection_ordered_ids(ctx)
    if len(ordered) < 2:
        return []
    by_id = _segments_by_id(ctx)
    bridges: dict[str, Any] | None = None
    if ctx.artifact_exists("understanding/reorder_bridges.json"):
        try:
            loaded = ctx.read_json("understanding/reorder_bridges.json")
            if isinstance(loaded, dict):
                bridges = loaded
        except Exception:
            bridges = None
    if bridges is None:
        try:
            from interview_mux.reorder_bridges import build_reorder_bridges
            from interview_mux.bridge_voice_policy import annotate_reorder_bridges

            bridges = annotate_reorder_bridges(
                build_reorder_bridges(ordered, by_id),
                narrative_mode=None,
                episode_vo_shape=None,
            )
        except Exception:
            try:
                from interview_mux.reorder_bridges import build_reorder_bridges

                bridges = build_reorder_bridges(ordered, by_id)
            except Exception:
                bridges = {"pairs": []}
    gap = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else {}
    )
    if transitions_doc is not None:
        transitions = transitions_doc
    elif ctx.artifact_exists("master/transitions.json"):
        try:
            transitions = ctx.read_json("master/transitions.json")
        except Exception:
            transitions = {"transitions": []}
    else:
        transitions = {"transitions": []}
    edl = (
        ctx.read_json("master/edl.json")
        if ctx.artifact_exists("master/edl.json")
        else None
    )
    required: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    try:
        from interview_mux.bridge_completeness import missing_reorder_bridges

        for row in missing_reorder_bridges(
            bridges if isinstance(bridges, dict) else None,
            gap_report=gap if isinstance(gap, dict) else None,
            transitions=transitions if isinstance(transitions, dict) else None,
            justified_skip_before_ids=_justified_skip_before_ids(ctx),
            edl=edl if isinstance(edl, dict) else None,
        ):
            if not isinstance(row, dict):
                continue
            a = str(row.get("after_segment_id") or row.get("after_id") or "")
            b = str(row.get("before_segment_id") or row.get("before_id") or "")
            if a and b and (a, b) not in seen:
                seen.add((a, b))
                required.append((a, b))
    except Exception:
        pass
    if isinstance(edl, dict):
        for clip in edl.get("clips") or []:
            if not isinstance(clip, dict) or str(clip.get("type") or "") != "transition":
                continue
            a = str(clip.get("after_segment_id") or "")
            b = str(clip.get("before_segment_id") or "")
            if a and b and (a, b) not in seen:
                if b in _justified_skip_before_ids(ctx):
                    continue
                seen.add((a, b))
                required.append((a, b))
    freeze = frozen_transition_pair_keys(ctx)
    if freeze and ordered:
        adj = {(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1)}
        for key in freeze:
            parsed = _parse_pair_key(key)
            if not parsed:
                continue
            if parsed in adj and parsed not in seen:
                if parsed[1] in _justified_skip_before_ids(ctx):
                    continue
                seen.add(parsed)
                required.append(parsed)
    return required


def _recover_transition_text(
    ctx: RunContext, after_id: str, before_id: str
) -> str:
    """Best-effort spoken text for a required pair that was dropped from inventory."""
    lid = _transition_line_id(after_id, before_id)
    if ctx.artifact_exists("master/edl.json"):
        try:
            edl = ctx.read_json("master/edl.json")
            for clip in ((edl or {}).get("clips") or []):
                if not isinstance(clip, dict) or str(clip.get("type") or "") != "transition":
                    continue
                if (
                    str(clip.get("after_segment_id") or "") == after_id
                    and str(clip.get("before_segment_id") or "") == before_id
                ):
                    text = str(clip.get("text") or "").strip()
                    if text:
                        return text
        except Exception:
            pass
    try:
        from interview_mux.vo_synthesis_audit import synthesis_entry_for_line

        entry = synthesis_entry_for_line(ctx, lid)
        if entry:
            text = str(entry.get("normalized_script") or "").strip()
            if text:
                return text
    except Exception:
        pass
    try:
        from interview_mux.seam_glue import default_bridge_text, enrich_bridge_pair_excerpts

        pair = enrich_bridge_pair_excerpts(
            {
                "after_segment_id": after_id,
                "before_segment_id": before_id,
            },
            _segments_by_id(ctx),
        )
        return str(default_bridge_text(pair) or "").strip()
    except Exception:
        return ""


def retain_required_transition_pairs(
    ctx: RunContext, doc: dict[str, Any] | None
) -> tuple[dict[str, Any], list[str]]:
    """Re-insert adjacency/EDL-required pairs that a rewrite would drop."""
    base = dict(doc) if isinstance(doc, dict) else {"transitions": []}
    items = [dict(r) for r in (base.get("transitions") or []) if isinstance(r, dict)]
    present = {
        (
            str(r.get("after_segment_id") or ""),
            str(r.get("before_segment_id") or ""),
        )
        for r in items
        if str(r.get("after_segment_id") or "") and str(r.get("before_segment_id") or "")
    }
    restored: list[str] = []
    # Evaluate required pairs against the *incoming* doc so drops are detected.
    for after_id, before_id in adjacency_required_transition_pairs(
        ctx, transitions_doc=base
    ):
        if (after_id, before_id) in present:
            for row in items:
                if (
                    str(row.get("after_segment_id") or "") == after_id
                    and str(row.get("before_segment_id") or "") == before_id
                ):
                    if not str(row.get("text") or "").strip():
                        text = _recover_transition_text(ctx, after_id, before_id)
                        if text:
                            row["text"] = text
                            restored.append(f"{after_id}->{before_id}:refilled_text")
                    break
            continue
        text = _recover_transition_text(ctx, after_id, before_id)
        if not text:
            continue
        items.append(
            {
                "after_segment_id": after_id,
                "before_segment_id": before_id,
                "text": text,
                "type": "bridge",
                "retained_required_adjacency": True,
            }
        )
        present.add((after_id, before_id))
        restored.append(f"{after_id}->{before_id}")
    out = dict(base)
    out["transitions"] = items
    return out, restored


def persist_transitions_doc(
    ctx: RunContext,
    doc: dict[str, Any] | None,
    *,
    stage_key: str | None = None,
    skip_handoff: bool = False,
) -> dict[str, Any]:
    """Write ``master/transitions.json`` after retaining adjacency-required pairs."""
    from interview_mux.artifact_sanitize.one_writer import commit_transitions_doc

    retained_path = commit_transitions_doc(
        ctx,
        dict(doc or {"transitions": []}),
        stage_key=stage_key,
        skip_handoff=skip_handoff,
        reason=stage_key or "persist_transitions_doc",
    )
    try:
        loaded = ctx.read_json("master/transitions.json")
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    # Fallback — path was written; return input shape
    _ = retained_path
    return dict(doc or {"transitions": []})


def _pre_mix_window(ctx: RunContext) -> bool:
    """True once EDL/transitions exist and mix has not produced assembly yet."""
    if ctx.artifact_exists("master/assembly.wav"):
        # Post-mix: still allow path canonicalization, but pair restore is pre-mix.
        return False
    return ctx.artifact_exists("master/edl.json") or ctx.artifact_exists(
        "master/transitions.json"
    )


def ensure_pre_mix_transition_integrity(
    ctx: RunContext, *, synthesize: bool = True
) -> dict[str, Any]:
    """Keep/regenerate adjacency-required spoken transitions and fix artifact paths.

    Call before mix (and after any transitions.json rewrite). Never leave EDL
    clips or synthesis audits pointing at dead pending paths when committed WAVs
    exist; never drop a required adjacency pair from inventory.
    """
    report: dict[str, Any] = {
        "retained": [],
        "synthesized": [],
        "paths_rewritten": [],
        "edl_restamped": False,
    }
    if not ctx.artifact_exists("master/transitions.json") and not ctx.artifact_exists(
        "master/edl.json"
    ):
        return report

    doc: dict[str, Any] = {"transitions": []}
    if ctx.artifact_exists("master/transitions.json"):
        try:
            loaded = ctx.read_json("master/transitions.json")
            if isinstance(loaded, dict):
                doc = loaded
        except Exception:
            doc = {"transitions": []}

    if _pre_mix_window(ctx) or ctx.artifact_exists("master/edl.json"):
        retained, notes = retain_required_transition_pairs(ctx, doc)
        if notes:
            report["retained"] = notes
            ctx.write_json("master/transitions.json", retained, skip_handoff=True)
            doc = retained

    if synthesize and (_pre_mix_window(ctx) or current_transition_pairs_missing(ctx)):
        needed: set[tuple[str, str]] = set()
        for after_id, before_id in spoken_transition_pairs(ctx):
            if resolve_transition_wav(ctx, after_id, before_id) is None:
                needed.add((after_id, before_id))
        for after_id, before_id in adjacency_required_transition_pairs(ctx):
            if resolve_transition_wav(ctx, after_id, before_id) is None:
                needed.add((after_id, before_id))
        if needed:
            for after_id, before_id in needed:
                _purge_transition_pair_wav(ctx, after_id, before_id)
            try:
                synthesize_spoken_transitions(ctx, pairs=needed)
                report["synthesized"] = [f"{a}->{b}" for a, b in sorted(needed)]
            except Exception as exc:
                ctx.log(
                    f"pre-mix transition synth incomplete: {exc}",
                    level="warning",
                    stage="mix",
                )

    try:
        from interview_mux.write_staging import promote_staged_side_effects

        promote_staged_side_effects(ctx, ("master/transitions/",))
    except Exception:
        pass

    try:
        from interview_mux.vo_synthesis_audit import canonicalize_synthesis_out_wav_paths

        report["paths_rewritten"] = canonicalize_synthesis_out_wav_paths(ctx)
    except Exception:
        pass

    try:
        report["edl_restamped"] = bool(restamp_edl_transition_source_paths(ctx))
    except Exception:
        pass

    if report["retained"] or report["synthesized"] or report["paths_rewritten"]:
        ctx.log(
            "pre-mix transition integrity: "
            f"retained={len(report['retained'])} "
            f"synth={len(report['synthesized'])} "
            f"paths={len(report['paths_rewritten'])}",
            level="info",
            stage="mix",
            detail=report,
        )
    return report
