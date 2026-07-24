"""Source topology classification and flow adaptation for TBIY-style production."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.audio_clips import extract_clip
from interview_mux.config import merged_config
from interview_mux.operator_trace import logged_step
from interview_mux.production_profile import TBIY_STYLE, get_production_style, is_tbiy
from interview_mux.run_context import RunContext
from interview_mux.conversation_context import role_is_content, role_is_frame


TOPOLOGY_CLASSES = (
    "one_on_one_asymmetric",
    "one_on_one_balanced",
    "panel_multi_guest",
    "co_host_frame",
    "multi_idea_sparse_host",
    "monologue_heavy",
)


def _thresholds() -> dict[str, Any]:
    cfg = merged_config().get("source_topology") or {}
    return dict(cfg.get("thresholds") or {})


def _speaker_talk_stats(transcript: dict[str, Any], speakers_doc: dict[str, Any]) -> list[dict[str, Any]]:
    words = transcript.get("words") or []
    speakers = speakers_doc.get("speakers") or []
    by_id: dict[str, dict[str, Any]] = {}
    for sp in speakers:
        if not isinstance(sp, dict):
            continue
        sid = str(sp.get("speaker_id") or sp.get("id") or "")
        if not sid:
            continue
        by_id[sid] = {
            "speaker_id": sid,
            "role_hint": sp.get("role") or sp.get("role_hint") or "unknown",
            "talk_ms": 0,
            "word_count": 0,
            "turn_count": 0,
            "question_count": 0,
        }
    if not by_id and words:
        labels = sorted({str(w.get("speaker")) for w in words if w.get("speaker") is not None})
        for label in labels:
            by_id[label] = {
                "speaker_id": label,
                "role_hint": "unknown",
                "talk_ms": 0,
                "word_count": 0,
                "turn_count": 0,
                "question_count": 0,
            }

    prev_speaker: str | None = None
    for w in words:
        if not isinstance(w, dict):
            continue
        sid = str(w.get("speaker") or w.get("speaker_id") or "")
        if sid not in by_id:
            by_id[sid] = {
                "speaker_id": sid,
                "role_hint": "unknown",
                "talk_ms": 0,
                "word_count": 0,
                "turn_count": 0,
                "question_count": 0,
            }
        start = float(w.get("start_ms") or w.get("start") or 0)
        end = float(w.get("end_ms") or w.get("end") or start)
        dur = max(0.0, end - start)
        by_id[sid]["talk_ms"] += dur
        by_id[sid]["word_count"] += 1
        text = str(w.get("word") or w.get("text") or "")
        if "?" in text:
            by_id[sid]["question_count"] += 1
        if sid != prev_speaker:
            by_id[sid]["turn_count"] += 1
            prev_speaker = sid

    total_ms = sum(s["talk_ms"] for s in by_id.values()) or 1.0
    rows = []
    for row in by_id.values():
        row["talk_ratio"] = round(row["talk_ms"] / total_ms, 4)
        turns = max(1, row["turn_count"])
        row["avg_turn_ms"] = round(row["talk_ms"] / turns, 1)
        rows.append(row)
    rows.sort(key=lambda r: r["talk_ms"], reverse=True)
    return rows


def _role_is_content(role: str) -> bool:
    return role_is_content(role)


def _role_is_frame(role: str) -> bool:
    return role_is_frame(role)


def _format_class_from_doc(speakers_doc: dict[str, Any]) -> str | None:
    profile = speakers_doc.get("conversation_profile") or {}
    if isinstance(profile, dict):
        fc = profile.get("format_class_candidate")
        if isinstance(fc, str) and fc:
            return fc
    return None


def classify_topology(stats: list[dict[str, Any]], speakers_doc: dict[str, Any]) -> str:
    th = _thresholds()
    format_hint = _format_class_from_doc(speakers_doc)
    speakers = speakers_doc.get("speakers") or []
    if format_hint == "panel":
        panelists = [s for s in speakers if isinstance(s, dict) and str(s.get("role", "")).lower() == "panelist"]
        content = [s for s in speakers if isinstance(s, dict) and role_is_content(str(s.get("role", "")))]
        if len(panelists) >= 2 or len(content) >= 2:
            return "panel_multi_guest"
    if format_hint == "debate" and len(stats) >= 2:
        return "one_on_one_balanced"
    if format_hint in ("fireside", "media_profile") and stats and stats[0].get("talk_ratio", 0) >= float(
        th.get("monologue_talk_ratio", 0.80) * 0.9
    ):
        return "monologue_heavy"
    if any(isinstance(sp, dict) and str(sp.get("role", "")).lower() == "co_host" for sp in speakers):
        return "co_host_frame"

    mono_ratio = float(th.get("monologue_talk_ratio", 0.80))
    asymmetric_ratio = float(th.get("asymmetric_content_ratio", 0.65))
    balanced_low = float(th.get("balanced_talk_ratio_low", 0.40))
    balanced_high = float(th.get("balanced_talk_ratio_high", 0.60))
    panel_guest_min = int(th.get("panel_guest_min", 2))

    if not stats:
        return "one_on_one_asymmetric"

    content = [s for s in stats if _role_is_content(str(s.get("role_hint")))]
    frame = [s for s in stats if _role_is_frame(str(s.get("role_hint")))]
    if not content and not frame:
        speakers = speakers_doc.get("speakers") or []
        for sp in speakers:
            if not isinstance(sp, dict):
                continue
            sid = str(sp.get("speaker_id") or "")
            role = str(sp.get("role") or "")
            for row in stats:
                if row["speaker_id"] == sid:
                    row["role_hint"] = role
        content = [s for s in stats if _role_is_content(str(s.get("role_hint")))]
        frame = [s for s in stats if _role_is_frame(str(s.get("role_hint")))]

    if len(stats) == 1 or stats[0]["talk_ratio"] >= mono_ratio:
        return "monologue_heavy"

    if len(content) >= panel_guest_min:
        return "panel_multi_guest"

    if len(frame) >= 2:
        return "co_host_frame"

    if len(stats) >= 2:
        top, second = stats[0], stats[1]
        if balanced_low <= top["talk_ratio"] <= balanced_high and balanced_low <= second["talk_ratio"] <= balanced_high:
            return "one_on_one_balanced"
        if _role_is_content(str(top.get("role_hint"))) and top["talk_ratio"] >= asymmetric_ratio:
            return "one_on_one_asymmetric"

    topic_count = len(speakers_doc.get("topics") or [])
    if topic_count == 0 and len(stats) >= 2:
        frame_talk = sum(s["talk_ratio"] for s in frame)
        if frame_talk < float(th.get("sparse_host_frame_ratio", 0.15)):
            return "multi_idea_sparse_host"

    return "one_on_one_asymmetric"


def _segmentation_policy(topology_class: str) -> dict[str, Any]:
    from interview_mux.segment_timeline_standard import resolved_segmentation_policy

    _ = topology_class
    return resolved_segmentation_policy()


def _ranking_weights(topology_class: str) -> dict[str, float]:
    base = {
        "narrative_arc_fit": 0.30,
        "claim_impact": 0.25,
        "reaction_opportunity": 0.20,
        "topic_coherence": 0.25,
    }
    if topology_class == "multi_idea_sparse_host":
        base["claim_impact"] = 0.35
        base["topic_coherence"] = 0.30
        base["narrative_arc_fit"] = 0.20
    elif topology_class == "monologue_heavy":
        base["reaction_opportunity"] = 0.10
        base["narrative_arc_fit"] = 0.40
    return base


def _sfx_density(topology_class: str) -> dict[str, int]:
    densities = {
        "multi_idea_sparse_host": {"max_punctuators": 5, "max_beds": 1, "max_foley": 2},
        "monologue_heavy": {"max_punctuators": 2, "max_beds": 3, "max_foley": 2},
        "panel_multi_guest": {"max_punctuators": 3, "max_beds": 2, "max_foley": 2},
    }
    default = {"max_punctuators": 4, "max_beds": 2, "max_foley": 2}
    return dict(densities.get(topology_class, default))


def _tbiy_role_map(stats: list[dict[str, Any]], pickup_id: str) -> dict[str, Any]:
    content = [s for s in stats if _role_is_content(str(s.get("role_hint")))]
    frame = [s for s in stats if _role_is_frame(str(s.get("role_hint")))]
    storytellers = [s["speaker_id"] for s in (content or stats[:1])]
    reactors = [s["speaker_id"] for s in frame if s["speaker_id"] != pickup_id]
    analytical = None
    if frame:
        analytical = max(frame, key=lambda s: s.get("question_count", 0)).get("speaker_id")
    return {
        "primary_storyteller_speaker_ids": storytellers,
        "reactor_speaker_ids": reactors,
        "analytical_lens_speaker_id": analytical,
        "pickup_eligible_speaker_id": pickup_id,
    }


def build_topology_artifacts(
    ctx: RunContext,
    *,
    overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    transcript = ctx.read_json("transcript/full.json")
    speakers_doc = ctx.read_json("understanding/speakers.json")
    stats = _speaker_talk_stats(transcript, speakers_doc)
    least = min(stats, key=lambda s: s["talk_ms"])["speaker_id"] if stats else "spk_0"
    topology_class = classify_topology(stats, speakers_doc)
    seg_policy = _segmentation_policy(topology_class)
    if overrides:
        seg_policy.update({k: v for k, v in overrides.items() if v is not None})

    style = get_production_style(ctx)
    role_map = _tbiy_role_map(stats, least)
    topic_count = len(speakers_doc.get("topics") or []) if isinstance(speakers_doc, dict) else 0
    topology = {
        "topology_class": topology_class,
        "speaker_stats": stats,
        "least_spoken_speaker_id": least,
        "pickup_eligible_speaker_id": least,
        "tbiy_role_map": role_map,
        "segmentation_policy": seg_policy,
        "classified_at": datetime.now(timezone.utc).isoformat(),
        "production_style": style,
    }
    adaptation = {
        "topology_class": topology_class,
        "production_style": style,
        "ranking_weights": _ranking_weights(topology_class),
        "sfx_density": _sfx_density(topology_class),
        "segmentation_policy": seg_policy,
        "operator_overrides": {
            "segmentation_granularity": None,
            "force_resegment": False,
            "topology_confirmed": False,
            "pickup_speaker_confirmed": False,
        },
        "pickup_eligible_speaker_id": least,
        "summary_plain": (
            f"Classified as {topology_class.replace('_', ' ')}. "
            f"Gap pickup voice defaults to least-spoken speaker ({least})."
        ),
    }
    if style == TBIY_STYLE or is_tbiy(ctx):
        from interview_mux.tbiy_conformance import (
            apply_conformance_to_adaptation,
            build_conformance_plan,
        )

        plan = build_conformance_plan(
            topology_class=topology_class,
            stats=stats,
            role_map=role_map,
            pickup_id=least,
            topic_count=topic_count,
            ctx=ctx,
        )
        adaptation = apply_conformance_to_adaptation(
            adaptation,
            plan,
            base_ranking=adaptation.get("ranking_weights"),
            base_sfx=adaptation.get("sfx_density"),
        )
    return topology, adaptation


def load_topology(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("understanding/source_topology.json"):
        return None
    return ctx.read_json("understanding/source_topology.json")


def load_flow_adaptation(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("understanding/flow_adaptation.json"):
        return None
    return ctx.read_json("understanding/flow_adaptation.json")


def pickup_eligible_speaker_id(ctx: RunContext) -> str | None:
    topo = load_topology(ctx)
    if isinstance(topo, dict) and topo.get("pickup_eligible_speaker_id"):
        return str(topo["pickup_eligible_speaker_id"])
    adapt = load_flow_adaptation(ctx)
    if isinstance(adapt, dict) and adapt.get("pickup_eligible_speaker_id"):
        return str(adapt["pickup_eligible_speaker_id"])
    return None


def pickup_speaker_confirmed(ctx: RunContext) -> bool:
    adapt = load_flow_adaptation(ctx)
    if not isinstance(adapt, dict):
        return False
    overrides = adapt.get("operator_overrides") or {}
    return bool(overrides.get("pickup_speaker_confirmed"))


def check_pickup_speaker_pending(ctx: RunContext) -> bool:
    """True when topology exists but operator has not confirmed gap pickup speaker."""
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
    from interview_mux.gap_vo_gates import check_gap_framing_decision_pending, gap_framing_enabled

    if gap_fill_was_skipped(ctx) or not gap_framing_enabled(ctx):
        return False
    if check_gap_framing_decision_pending(ctx):
        return False
    if pickup_speaker_confirmed(ctx):
        return False
    if not ctx.artifact_exists("understanding/source_topology.json"):
        return False
    if not ctx.is_done("source_topology_build"):
        return False
    if ctx.is_done("missing_framing"):
        return False
    from interview_mux.pipeline import ANALYSIS_ORDER

    idx = ANALYSIS_ORDER.index("missing_framing")
    for sid in ANALYSIS_ORDER[:idx]:
        if not ctx.is_done(sid):
            return False
    return True


def require_pickup_speaker_clear(ctx: RunContext) -> None:
    if check_pickup_speaker_pending(ctx):
        ctx.log(
            "Gap pickup speaker must be confirmed before gap evaluation. "
            "Open missing framing in the GUI, listen to speaker samples, and confirm.",
            level="error",
            stage="missing_framing",
        )
        raise SystemExit(
            "Gap pickup speaker gate: confirm who will record gap-fill lines in the GUI "
            f"→ {ctx.path('understanding/flow_adaptation.json')}"
        )


def _speaker_ids_from_stats(stats: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("speaker_id") or "") for row in stats if row.get("speaker_id")}


def _apply_pickup_speaker(
    topology: dict[str, Any],
    adaptation: dict[str, Any],
    speaker_id: str,
) -> None:
    stats = list(topology.get("speaker_stats") or [])
    topology["pickup_eligible_speaker_id"] = speaker_id
    topology["tbiy_role_map"] = _tbiy_role_map(stats, speaker_id)
    adaptation["pickup_eligible_speaker_id"] = speaker_id
    least = str(topology.get("least_spoken_speaker_id") or speaker_id)
    default_note = " (default — least speech)" if speaker_id == least else ""
    conf = adaptation.get("tbiy_conformance") if isinstance(adaptation.get("tbiy_conformance"), dict) else None
    if conf and isinstance(conf.get("summary_plain"), str) and conf["summary_plain"].strip():
        adaptation["summary_plain"] = (
            f"{conf['summary_plain'].strip()} Gap pickup voice: {speaker_id}{default_note}."
        )
    else:
        adaptation["summary_plain"] = (
            f"Classified as {str(topology.get('topology_class', '')).replace('_', ' ')}. "
            f"Gap pickup voice: {speaker_id}{default_note}."
        )


def _find_speaker_sample_ms(transcript: dict[str, Any], speaker_id: str) -> tuple[int, int] | None:
    words = transcript.get("words") or []
    min_ms = 3000
    max_ms = 15000
    best: tuple[int, int] | None = None
    best_dur = 0
    turn_start: int | None = None
    turn_end: int | None = None
    turn_speaker: str | None = None

    def _consider_turn(start: int | None, end: int | None, sid: str | None) -> None:
        nonlocal best, best_dur
        if sid != speaker_id or start is None or end is None:
            return
        dur = max(0, end - start)
        if dur >= min_ms and dur <= max_ms and dur > best_dur:
            best = (start, end)
            best_dur = dur
        elif dur > max_ms and best is None:
            best = (start, start + max_ms)
            best_dur = max_ms

    for w in words:
        if not isinstance(w, dict):
            continue
        sid = str(w.get("speaker") or w.get("speaker_id") or "")
        start = int(float(w.get("start_ms") or w.get("start") or 0))
        end = int(float(w.get("end_ms") or w.get("end") or start))
        if sid != turn_speaker:
            _consider_turn(turn_start, turn_end, turn_speaker)
            turn_speaker = sid
            turn_start = start
            turn_end = end
        else:
            turn_end = end
    _consider_turn(turn_start, turn_end, turn_speaker)

    if best is not None:
        return best

    sp_words = [
        w
        for w in words
        if isinstance(w, dict) and str(w.get("speaker") or w.get("speaker_id") or "") == speaker_id
    ]
    if not sp_words:
        return None
    start = int(float(sp_words[0].get("start_ms") or sp_words[0].get("start") or 0))
    end = int(float(sp_words[-1].get("end_ms") or sp_words[-1].get("end") or start))
    end = min(end, start + max_ms)
    if end - start < 500:
        return None
    return start, end


def ensure_speaker_sample_clips(ctx: RunContext) -> dict[str, str]:
    """Return speaker_id → relative clip path; extract WAV samples on demand."""
    topo = load_topology(ctx) or {}
    stats = topo.get("speaker_stats") or []
    if not stats:
        return {}
    if not ctx.artifact_exists("transcript/full.json"):
        return {}
    audio = ctx.read_path("ingest", "normalized.wav")
    if not audio.is_file():
        return {}
    transcript = ctx.read_json("transcript/full.json")
    out: dict[str, str] = {}
    for row in stats:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("speaker_id") or "")
        if not sid:
            continue
        rel = f"understanding/speaker_samples/{sid}.wav"
        dest = ctx.path(*rel.split("/"))
        if dest.is_file():
            out[sid] = rel
            continue
        sample = _find_speaker_sample_ms(transcript, sid)
        if not sample:
            continue
        start_ms, end_ms = sample
        extract_clip(audio, dest, start_ms, end_ms)
        ref_words = [
            str(w.get("text") or "")
            for w in (transcript.get("words") or [])
            if isinstance(w, dict)
            and str(w.get("speaker_id") or w.get("speaker") or "") == sid
            and int(float(w.get("start_ms") or w.get("start") or 0)) >= start_ms
            and int(float(w.get("end_ms") or w.get("end") or 0)) <= end_ms
        ]
        ref_text = " ".join(ref_words).strip()
        if ref_text:
            sidecar = ctx.path("understanding", "speaker_samples", f"{sid}.json")
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(
                json.dumps(
                    {
                        "speaker_id": sid,
                        "ref_text": ref_text,
                        "wav": rel,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        out[sid] = rel
    return out


def pickup_speaker_payload(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

    topo = load_topology(ctx) or {}
    adapt = load_flow_adaptation(ctx) or {}
    stats = list(topo.get("speaker_stats") or [])
    clips = ensure_speaker_sample_clips(ctx)
    least = str(topo.get("least_spoken_speaker_id") or "")
    selected = str(adapt.get("pickup_eligible_speaker_id") or least or "")
    speakers: list[dict[str, Any]] = []
    for row in stats:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("speaker_id") or "")
        if not sid:
            continue
        talk_ms = float(row.get("talk_ms") or 0)
        speakers.append(
            {
                **row,
                "talk_minutes": round(talk_ms / 60_000, 2),
                "is_least_spoken": sid == least,
                "sample_clip_path": clips.get(sid),
                "sample_start_ms": None,
                "sample_end_ms": None,
            }
        )
    return {
        "speakers": speakers,
        "least_spoken_speaker_id": least,
        "pickup_eligible_speaker_id": selected,
        "pickup_speaker_confirmed": pickup_speaker_confirmed(ctx),
        "gap_fill_skipped": gap_fill_was_skipped(ctx),
        "pending": check_pickup_speaker_pending(ctx),
    }


def attach_adaptation_to_payload(ctx: RunContext, payload: dict[str, Any]) -> dict[str, Any]:
    from interview_mux.conversation_context import attach_conversation_context

    payload = attach_conversation_context(ctx, payload, "")
    topo = load_topology(ctx)
    adapt = load_flow_adaptation(ctx)
    if topo:
        payload["source_topology"] = topo
    if adapt:
        payload["flow_adaptation"] = adapt
    if is_tbiy(ctx):
        payload["production_style"] = TBIY_STYLE
        from interview_mux.tbiy_conformance import attach_conformance_to_payload

        payload = attach_conformance_to_payload(ctx, payload)
    return payload


def run_source_topology_build(ctx: RunContext) -> None:
    with logged_step("source_topology/classify", ctx=ctx, stage="source_topology_build"):
        existing_adapt = load_flow_adaptation(ctx)
        preserved_pickup: str | None = None
        if isinstance(existing_adapt, dict):
            overrides = existing_adapt.get("operator_overrides") or {}
            if overrides.get("pickup_speaker_confirmed"):
                preserved_pickup = str(existing_adapt.get("pickup_eligible_speaker_id") or "") or None
            elif existing_adapt.get("pickup_eligible_speaker_id"):
                preserved_pickup = str(existing_adapt.get("pickup_eligible_speaker_id"))

        topology, adaptation = build_topology_artifacts(ctx)
        if preserved_pickup and preserved_pickup in _speaker_ids_from_stats(topology.get("speaker_stats") or []):
            _apply_pickup_speaker(topology, adaptation, preserved_pickup)
            if isinstance(existing_adapt, dict):
                adaptation["operator_overrides"] = {
                    **(adaptation.get("operator_overrides") or {}),
                    **(existing_adapt.get("operator_overrides") or {}),
                }

        ctx.write_json("understanding/source_topology.json", topology, stage_key="source_topology_build")
        ctx.write_json("understanding/flow_adaptation.json", adaptation, stage_key="source_topology_build")
        ctx.mark_done("source_topology_build")
        maybe_auto_confirm_pickup_speaker(ctx)
        conf = adaptation.get("tbiy_conformance") if isinstance(adaptation.get("tbiy_conformance"), dict) else {}
        score = conf.get("score") if isinstance(conf.get("score"), dict) else {}
        modes = conf.get("modes") if isinstance(conf.get("modes"), dict) else {}
        ctx.log(
            f"Source topology: {topology['topology_class']} — pickup voice {topology['pickup_eligible_speaker_id']}"
            + (
                f" — TBIY conformance {int(float(score.get('ratio') or 0) * 100)}%"
                f" (acts={modes.get('five_act_mode')}, moat={modes.get('moat_mode')})"
                if conf
                else ""
            ),
            level="success",
            stage="source_topology_build",
            detail={
                "kind": "adaptation",
                "journey_kind": "adaptation",
                "topology_class": topology["topology_class"],
                "pickup_eligible_speaker_id": topology["pickup_eligible_speaker_id"],
                "production_style": topology.get("production_style"),
                "segmentation_policy": topology.get("segmentation_policy"),
                "tbiy_conformance_score": score.get("ratio") if conf else None,
                "five_act_mode": modes.get("five_act_mode"),
                "moat_mode": modes.get("moat_mode"),
                "vo_bridge_priority": modes.get("vo_bridge_priority"),
            },
        )


def maybe_auto_confirm_pickup_speaker(ctx: RunContext) -> bool:
    """v2: operator confirms pickup speaker explicitly."""
    return False


def apply_flow_adaptation_patch(ctx: RunContext, patch: dict[str, Any]) -> dict[str, Any]:
    adapt = load_flow_adaptation(ctx) or {}
    overrides = dict(adapt.get("operator_overrides") or {})
    overrides.update(patch.get("operator_overrides") or {})
    adapt["operator_overrides"] = overrides
    if patch.get("segmentation_policy"):
        adapt["segmentation_policy"] = {**adapt.get("segmentation_policy", {}), **patch["segmentation_policy"]}

    pickup_id = patch.get("pickup_eligible_speaker_id")
    topo = ctx.read_json("understanding/source_topology.json") if ctx.artifact_exists("understanding/source_topology.json") else {}
    if not isinstance(topo, dict):
        topo = {}
    if pickup_id is not None:
        speaker_id = str(pickup_id)
        stats = topo.get("speaker_stats") or []
        if speaker_id not in _speaker_ids_from_stats(stats if isinstance(stats, list) else []):
            raise ValueError(f"Unknown speaker_id: {speaker_id}")
        _apply_pickup_speaker(topo, adapt, speaker_id)

    ctx.write_json("understanding/flow_adaptation.json", adapt)
    if ctx.artifact_exists("understanding/source_topology.json") and isinstance(topo, dict):
        if patch.get("segmentation_policy"):
            topo["segmentation_policy"] = adapt["segmentation_policy"]
        if pickup_id is not None:
            ctx.write_json("understanding/source_topology.json", topo)
    ctx.log(
        "Flow adaptation updated by operator",
        level="action",
        stage="source_topology_build",
        detail={"kind": "adaptation", "journey_kind": "adaptation", "patch": patch},
    )
    return adapt


def confirm_pickup_speaker(ctx: RunContext, *, speaker_id: str | None = None) -> dict[str, Any]:
    adapt = load_flow_adaptation(ctx) or {}
    topo = load_topology(ctx) or {}
    stats = topo.get("speaker_stats") or []
    valid = _speaker_ids_from_stats(stats if isinstance(stats, list) else [])
    selected = str(speaker_id or adapt.get("pickup_eligible_speaker_id") or topo.get("pickup_eligible_speaker_id") or "")
    if not selected or selected not in valid:
        raise ValueError("pickup_eligible_speaker_id is required and must match a known speaker")
    if not isinstance(topo, dict):
        topo = {}
    _apply_pickup_speaker(topo, adapt, selected)
    overrides = dict(adapt.get("operator_overrides") or {})
    overrides["pickup_speaker_confirmed"] = True
    adapt["operator_overrides"] = overrides
    ctx.write_json("understanding/flow_adaptation.json", adapt)
    if topo:
        ctx.write_json("understanding/source_topology.json", topo)
    ctx.log(
        f"Gap pickup speaker confirmed: {selected}",
        level="action",
        stage="missing_framing",
        detail={
            "kind": "adaptation",
            "journey_kind": "adaptation",
            "action_id": "gui.adaptation.pickup_speaker",
            "pickup_eligible_speaker_id": selected,
        },
    )
    return adapt
