from __future__ import annotations

import json
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.value_analysis.config import value_analysis_flag
from interview_mux.value_analysis.features_audio import extract_audio_features
from interview_mux.value_analysis.features_transcript import (
    VALUE_FEATURES_PATH,
    extract_transcript_features,
)


def _resolved_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    return cfg if cfg is not None else merged_config()


def _load_existing(ctx: RunContext, run_id: str) -> dict[str, Any]:
    if ctx.artifact_exists(VALUE_FEATURES_PATH):
        data = ctx.read_json(VALUE_FEATURES_PATH)
        if isinstance(data, dict):
            return data
    return {"version": 1, "run_id": run_id, "profiles": {}}


def profiles_for_flags(cfg: dict[str, Any] | None) -> list[str]:
    """Profile names enabled by value_analysis sub-flags (master must be on)."""
    resolved = _resolved_cfg(cfg)
    out: list[str] = []
    if value_analysis_flag(resolved, "transcript_features"):
        out.append("transcript")
    if value_analysis_flag(resolved, "audio_features"):
        out.append("audio")
    return out


def extract_and_write_value_features(
    ctx: RunContext,
    *,
    cfg: dict[str, Any] | None = None,
    profiles: tuple[str, ...] | None = None,
) -> list[str]:
    """Merge enabled profiles into understanding/value_features.json. Returns names written."""
    resolved = _resolved_cfg(cfg)
    run_id = ctx.run_id
    selected = list(profiles) if profiles is not None else profiles_for_flags(resolved)
    if not selected:
        return []

    out = _load_existing(ctx, run_id)
    out["version"] = 1
    out["run_id"] = run_id
    bucket = out.setdefault("profiles", {})
    if not isinstance(bucket, dict):
        bucket = {}
        out["profiles"] = bucket

    written: list[str] = []
    if "transcript" in selected:
        bucket["transcript"] = extract_transcript_features(ctx, cfg=resolved)
        written.append("transcript")
    if "audio" in selected:
        bucket["audio"] = extract_audio_features(ctx, cfg=resolved)
        written.append("audio")

    ctx.write_json(VALUE_FEATURES_PATH, out)
    return written


def maybe_auto_extract_value_features(ctx: RunContext, *, cfg: dict[str, Any] | None = None) -> list[str] | None:
    """After content_context when auto_extract_after_content_context is on; else no-op."""
    resolved = _resolved_cfg(cfg)
    if not value_analysis_flag(resolved, "auto_extract_after_content_context"):
        return None

    selected = profiles_for_flags(resolved)
    if "audio" in selected and not ctx.path("ingest", "normalized.wav").is_file():
        ctx.log(
            "value_analysis_skip_no_wav",
            level="warning",
            stage="content_context",
            detail=json.dumps(
                {"path": "ingest/normalized.wav", "skipped_profile": "audio"},
                ensure_ascii=False,
            ),
        )
        selected = [p for p in selected if p != "audio"]
    if not selected:
        return None

    written = extract_and_write_value_features(ctx, cfg=resolved, profiles=tuple(selected))
    if not written:
        return None

    ctx.log(
        "value_features_extracted",
        level="info",
        stage="content_context",
        detail=json.dumps({"profiles": written}, ensure_ascii=False),
    )
    return written


def maybe_enqueue_orchestration_investigations(
    ctx: RunContext,
    *,
    cfg: dict[str, Any] | None = None,
) -> int:
    """
    H-ORC-02: enqueue investigations when value features suggest acoustic/text ambiguity.
    H-ORC-03: topic_shift_hint boundary events aligned with transcript ambiguity.
    """
    resolved = _resolved_cfg(cfg)
    if not value_analysis_flag(resolved, "enabled"):
        return 0

    from interview_mux.analysis_memory import enqueue_investigations

    items: list[dict[str, Any]] = []

    if ctx.artifact_exists(VALUE_FEATURES_PATH):
        data = ctx.read_json(VALUE_FEATURES_PATH)
        profiles = data.get("profiles") if isinstance(data, dict) else {}
        transcript = profiles.get("transcript") if isinstance(profiles, dict) else {}
        flags = transcript.get("quality_trajectory_flags") if isinstance(transcript, dict) else []
        if not flags:
            from interview_mux.stage_enrichment import quality_trajectory_flags

            flags = quality_trajectory_flags(ctx)
        for flag in flags[:5]:
            if not isinstance(flag, dict):
                continue
            items.append(
                {
                    "kind": "acoustic_anomaly",
                    "question": flag.get("note", "Acoustic/text ambiguity flagged by value analysis."),
                    "priority": "medium",
                    "blocking": False,
                    "suggested_action": {"type": "rerun_stage", "stage": "content_context"},
                }
            )

    items.extend(_spine_orchestration_investigations(ctx))
    if items:
        enqueue_investigations(ctx, items, created_by_stage="content_context")
    return len(items)


def _spine_orchestration_investigations(ctx: RunContext) -> list[dict[str, Any]]:
    from interview_mux.interview_spine import SPINE_PATH
    from interview_mux.interview_spine.config import spine_enabled

    if not spine_enabled() or not ctx.artifact_exists(SPINE_PATH):
        return []

    spine = ctx.read_json(SPINE_PATH)
    if not isinstance(spine, dict):
        return []

    transcript = ctx.read_json("transcript/full.json") if ctx.artifact_exists("transcript/full.json") else {}
    low_conf_words = [
        w
        for w in (transcript.get("words") or [])
        if isinstance(w, dict) and float(w.get("confidence") or 1.0) < 0.75
    ]
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for event in spine.get("boundary_events") or []:
        if not isinstance(event, dict):
            continue
        etype = str(event.get("type") or "")
        time_ms = int(event.get("time_ms") or 0)
        key = f"{etype}:{time_ms}"
        if key in seen:
            continue

        if etype == "trust_dip":
            nearby = [
                w
                for w in low_conf_words
                if abs(int(w.get("start_ms", 0)) - time_ms) <= 2500
            ]
            if nearby:
                seen.add(key)
                items.append(
                    {
                        "kind": "acoustic_anomaly",
                        "question": (
                            f"Trust dip near {time_ms // 1000}s with low-confidence words — "
                            "verify transcript alignment."
                        ),
                        "priority": "medium",
                        "blocking": False,
                        "suggested_action": {"type": "rerun_stage", "stage": "transcript_review_build"},
                    }
                )
        elif etype == "topic_shift_hint":
            from interview_mux.coherence import coherence_active, replace_stub_topic_shift_hints

            if coherence_active() and replace_stub_topic_shift_hints():
                continue
            seen.add(key)
            items.append(
                {
                    "kind": "topic_drift",
                    "question": (
                        f"Topic shift hint near {time_ms // 1000}s — confirm brief themes still cover this turn."
                    ),
                    "priority": "low",
                    "blocking": False,
                    "suggested_action": {"type": "rerun_stage", "stage": "content_context"},
                }
            )
    return items[:6]
