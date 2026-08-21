from __future__ import annotations

from typing import Any

from interview_mux.interview_spine.boundaries import build_boundary_events
from interview_mux.interview_spine.clap_index import build_clap_index
from interview_mux.interview_spine.config import spine_cfg, spine_enabled
from interview_mux.interview_spine.features import build_speaker_stats, enrich_window_features
from interview_mux.interview_spine.lineage import build_derived_from, can_skip_rebuild
from interview_mux.interview_spine.windows import build_windows
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext


def run_interview_spine_build(ctx: RunContext) -> None:
    if not spine_enabled():
        ctx.log("Interview spine disabled in config.", level="info", stage="interview_spine_build")
        ctx.mark_done("interview_spine_build", force=True)
        return

    if not ctx.artifact_exists("transcript/full.json"):
        raise FileNotFoundError("transcript/full.json — run transcribe and complete G0 first.")
    if not ctx.artifact_exists("understanding/source_acoustic_profile.json"):
        raise FileNotFoundError(
            "understanding/source_acoustic_profile.json — run source_acoustic_profile first."
        )

    with logged_step("interview_spine_build/diarization_verify", ctx=ctx, stage="interview_spine_build"):
        try:
            from interview_mux.diarization_suspicion import run_diarization_verify

            run_diarization_verify(ctx, stage="interview_spine_build")
        except Exception as exc:  # noqa: BLE001 — fail-open keeps original labels
            ctx.log(
                f"Diarization verify fail-open: {exc}",
                level="warning",
                stage="interview_spine_build",
            )
            try:
                from interview_mux.homunculus.issues import emit_issue

                emit_issue(
                    ctx,
                    kind="diarization_verify_unavailable",
                    source="interview_spine_build",
                    stage_id="interview_spine_build",
                    implicated=["interview_spine_build"],
                    evidence={"reason": str(exc)[:300]},
                )
            except Exception:
                pass

    if can_skip_rebuild(ctx):
        ctx.log("Interview spine unchanged; skipping rebuild.", level="info", stage="interview_spine_build")
        ctx.mark_done("interview_spine_build")
        return

    cfg = spine_cfg()
    transcript = ctx.read_json("transcript/full.json")
    words = [w for w in (transcript.get("words") or []) if isinstance(w, dict)]
    sap = ctx.read_json("understanding/source_acoustic_profile.json")
    pace_class = str((sap.get("pacing") or {}).get("pace_class") or "conversational")

    preclean = ctx.read_path("preclean", "isolated.wav")
    wav_path = (
        preclean
        if preclean.is_file()
        else ctx.read_artifact_path(
            "ingest/normalized.wav",
            stage="interview_spine_build",
            label="normalized interview audio",
        )
    )

    window_sec = float(cfg.get("window_sec_default", 10))
    if pace_class == "dense":
        window_sec = float(cfg.get("window_sec_dense", 6))
    elif pace_class == "calm":
        window_sec = float(cfg.get("window_sec_calm", 12))

    windows = build_windows(words, pace_class=pace_class, cfg=cfg)
    with logged_step("interview_spine_build/enrich_windows", ctx=ctx, stage="interview_spine_build"):
        windows = enrich_window_features(
            windows,
            wav_path=wav_path,
            words=words,
            prosody_enabled=bool(cfg.get("prosody_enabled", True)),
        )

    segments = transcript.get("segments") or []
    with logged_step("interview_spine_build/boundary_events", ctx=ctx, stage="interview_spine_build"):
        boundary_events = build_boundary_events(
            words=words,
            windows=windows,
            wav_path=wav_path,
            segments=segments if isinstance(segments, list) else None,
            min_sources=int(cfg.get("boundary_fusion_min_sources", 1)),
        )

    retrieval_enabled = False
    sidecar_path: str | None = None
    vector_dim: int | None = None
    clap_model = str(cfg.get("clap_model_id", "laion/clap-htsat-fused"))
    with logged_step("interview_spine_build/clap_index", ctx=ctx, stage="interview_spine_build"):
        if cfg.get("clap_enabled", True):
            retrieval_enabled, sidecar_path, vector_dim = build_clap_index(
                ctx,
                windows,
                wav_path=wav_path,
                model_id=clap_model,
                timeout_sec=int(cfg.get("clap_timeout_sec", 120)),
            )
            if not retrieval_enabled:
                ctx.log(
                    "CLAP retrieval unavailable; spine written without embeddings.",
                    level="warning",
                    stage="interview_spine_build",
                )

    speaker_stats = build_speaker_stats(windows)
    for win in windows:
        win.pop("_words", None)

    doc: dict[str, Any] = {
        "schema_version": 1,
        "derived_from": build_derived_from(ctx),
        "encoders": {
            "dsp": "numpy_rms_v1",
            "clap": clap_model if retrieval_enabled else None,
            "ssl": None,
        },
        "window_policy": {
            "window_sec": window_sec,
            "hop_sec": float(cfg.get("hop_sec", 5)),
            "align_to": "words",
        },
        "windows": windows,
        "boundary_events": boundary_events,
        "retrieval": {
            "enabled": retrieval_enabled,
            "model_id": clap_model if retrieval_enabled else None,
            "sidecar_path": sidecar_path,
            "vector_dim": vector_dim,
            "window_count": len(windows),
        },
        "speaker_stats": speaker_stats,
    }

    from interview_mux.prompt_validation import validate_interview_spine

    errors = validate_interview_spine(doc)
    if errors:
        raise SystemExit(f"interview_spine validation failed: {errors[0]}")

    with logged_step("interview_spine_build/write", ctx=ctx, stage="interview_spine_build"):
        ctx.write_json("understanding/interview_spine.json", doc, stage_key="interview_spine_build")
    ctx.log(
        f"Interview spine complete — {len(windows)} windows, {len(boundary_events)} boundary events.",
        level="success",
        stage="interview_spine_build",
    )
    ctx.mark_done("interview_spine_build")
