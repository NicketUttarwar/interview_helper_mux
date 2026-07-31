"""Synthesize spoken chapter-transition bridges via the same VO path as gap lines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.creative_delivery import creative_delivery_required
from interview_mux.run_context import RunContext


def _transition_line_id(after_id: str, before_id: str) -> str:
    return f"tr_{after_id}_{before_id}"


def transition_wav_path(ctx: RunContext, after_id: str, before_id: str) -> Path:
    out_dir = ctx.path("master", "transitions")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{_transition_line_id(after_id, before_id)}.wav"


def resolve_transition_wav(
    ctx: RunContext, after_id: str, before_id: str
) -> Path | None:
    path = transition_wav_path(ctx, after_id, before_id)
    return path if path.is_file() else None


def synthesize_spoken_transitions(ctx: RunContext) -> list[dict[str, Any]]:
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
    from interview_mux.spoken_meta_lint import assert_speakable_or_raise

    # Prefer speaker_delivery_plan clone when present
    speaker_id = ""
    if ctx.artifact_exists("understanding/speaker_delivery_plan.json"):
        try:
            sdp = ctx.read_json("understanding/speaker_delivery_plan.json")
            if isinstance(sdp, dict):
                speaker_id = str(sdp.get("clone_speaker_id") or "")
        except Exception:
            speaker_id = ""
    if not speaker_id:
        speaker_id = pickup_eligible_speaker_id(ctx) or ""
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        try:
            assert_speakable_or_raise(text, context="transition")
        except ValueError as exc:
            raise ValueError(
                f"transition text blocked by spoken_meta_lint "
                f"({item.get('after_segment_id')}->{item.get('before_segment_id')}): {exc}"
            ) from exc
        after_id = str(item.get("after_segment_id") or "")
        before_id = str(item.get("before_segment_id") or "")
        if not after_id or not before_id:
            continue
        out = transition_wav_path(ctx, after_id, before_id)
        if out.is_file() and out.stat().st_size > 1000:
            results.append(
                {
                    "after_segment_id": after_id,
                    "before_segment_id": before_id,
                    "path": out.as_posix(),
                    "skipped": True,
                }
            )
            continue
        line = {
            "line_id": _transition_line_id(after_id, before_id),
            "text": text,
            "delivery": "synthesize",
            "targets_segment_id": after_id,
            "placement": "after",
            "voice_speaker_id": speaker_id or item.get("voice_speaker_id"),
            "suggested_tone": item.get("tone") or "bridge",
        }
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
            out.write_bytes(wav.read_bytes())
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
        if dur <= 0 or not src:
            after = clip.get("after_segment_id")
            before = clip.get("before_segment_id")
            bad.append(f"{after}->{before}")
    if bad:
        raise SystemExit(
            "edl: spoken transitions missing audio (duration_ms==0 or no source_path): "
            + ", ".join(bad[:8])
        )
