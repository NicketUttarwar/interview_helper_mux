from __future__ import annotations

import json
import math
from pathlib import Path

from interview_mux.config import merged_config
from interview_mux.master_qc import TARGETS, FlowName
from interview_mux.mastering_bus import measure_assembly_bus, target_lufs_for_flow
from interview_mux.operator_quality import record_qc_summary
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.sdp_cross_validate import validate_pre_master

def master_wav(ctx: RunContext, assembly_rel: str, master_rel: str, *, flow: str) -> Path:
    stage = "master_finalize"
    flow_name: FlowName = flow if flow in TARGETS else "podcast"
    thresholds = TARGETS[flow_name]
    cfg = merged_config()
    target = target_lufs_for_flow(flow_name, config=cfg)
    true_peak = float(thresholds.max_true_peak_dbtp)
    assembly = ctx.read_path(assembly_rel)
    master = ctx.path(master_rel)
    if not assembly.is_file():
        raise FileNotFoundError(assembly)
    if assembly.stat().st_size < 1024:
        raise RuntimeError(
            f"{stage}: assembly speech path is empty/corrupt ({assembly_rel}). "
            "Refuse master finalize — fix mix/speech stems before export."
        )

    with logged_step(f"{stage}/pre_master_validation", ctx=ctx, stage=stage):
        pre_errors = validate_pre_master(ctx, flow_name)
        if pre_errors:
            from interview_mux.coverage_limits import is_non_blocking_lint, pre_master_soft_fail_enabled

            blocking = [e for e in pre_errors if not is_non_blocking_lint(e)]
            soft_only = [e for e in pre_errors if is_non_blocking_lint(e)]
            if soft_only and pre_master_soft_fail_enabled():
                ctx.log(
                    f"pre_master soft warnings: {'; '.join(soft_only[:4])}",
                    level="warning",
                    stage=stage,
                    detail={"pre_master_soft_warnings": soft_only[:12]},
                )
            if blocking or not pre_master_soft_fail_enabled():
                summary = "; ".join((blocking or pre_errors)[:4])
                ctx.log(
                    f"pre_master validation failed: {summary}",
                    level="error",
                    stage=stage,
                    detail={"pre_master_validation": (blocking or pre_errors)[:12]},
                )
                record_qc_summary(
                    ctx,
                    "pre_master",
                    {
                        "passed": False,
                        "errors": (blocking or pre_errors)[:12],
                        "flow": flow_name,
                        "at_stage": stage,
                    },
                )
                raise RuntimeError(f"pre_master validation failed: {summary}")

    with logged_step(f"{stage}/measure_bus", ctx=ctx, stage=stage):
        bus = measure_assembly_bus(assembly)
        ctx.log(
            (
                f"Assembly bus measured {bus.integrated_lufs:.2f} LUFS "
                f"(target {target:.1f} ± {thresholds.tolerance_lufs:.1f}, "
                f"true-peak ceiling {true_peak:.1f} dBTP)"
            ),
            stage=stage,
            detail=(
                f"sample_rate_hz={bus.sample_rate_hz} channels={bus.channels} "
                f"duration_s={bus.duration_seconds:.2f}"
            ),
        )

    # Two-pass loudnorm: single-pass routinely undershoots long sparse podcasts
    # (this run landed at −18.9 vs −16 ±1.5). Probe measured_* then apply linear.
    with logged_step(f"{stage}/loudnorm_probe", ctx=ctx, stage=stage):
        measured = _ffmpeg_loudnorm_probe(
            assembly, target=target, true_peak=true_peak
        )
        ctx.log(
            (
                f"loudnorm probe input_i={measured.get('input_i')} "
                f"input_tp={measured.get('input_tp')} "
                f"target_offset={measured.get('target_offset')}"
            ),
            stage=stage,
        )
        loudnorm_filter = _master_filter_chain(
            cfg,
            target_lufs=target,
            true_peak_dbtp=true_peak,
            measured=measured,
        )

    with logged_step(f"{stage}/loudnorm_render", ctx=ctx, stage=stage):
        from interview_mux.operator_subprocess import run_command

        master.parent.mkdir(parents=True, exist_ok=True)
        run_command(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-y",
                "-i",
                str(assembly),
                "-af",
                loudnorm_filter,
                "-ar",
                "48000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(master),
            ],
            ctx=ctx,
            stage=stage,
            label=f"ffmpeg loudnorm master → {master_rel}",
            capture_output=True,
        )
    # End-E: refuse hollow/truncated master before marking finalize done.
    from interview_mux.delivery_invariants import (
        MIN_COMMITTED_MASTER_BYTES,
        committed_master_integrity_ok,
    )

    if not master.is_file() or master.stat().st_size < MIN_COMMITTED_MASTER_BYTES:
        raise RuntimeError(
            f"{stage}: master export truncated/corrupt ({master_rel} "
            f"size={master.stat().st_size if master.is_file() else 0}). "
            "Refuse mark_done — re-run finalize after a valid loudnorm render."
        )
    # The loudnorm render lands in this stage's staging root; the committed-master
    # invariant reads ``final_path``. Staging flush only happens *after* mark_done,
    # so the gate below could never pass and finalize looped forever on
    # "pending/truncated master cannot soft-complete" (exec_11871). Promote the
    # rendered bytes first — the gate then judges the real committed master.
    if not committed_master_integrity_ok(ctx):
        try:
            from interview_mux.write_staging import promote_staged_side_effects

            promoted = promote_staged_side_effects(
                ctx, (master_rel,), stage_id=stage
            )
            if promoted:
                ctx.log(
                    f"{stage}: promoted rendered master → {master_rel}",
                    stage=stage,
                )
        except Exception as exc:
            ctx.log(
                f"{stage}: could not promote rendered master ({exc})",
                level="warning",
                stage=stage,
            )
    if not committed_master_integrity_ok(ctx):
        raise RuntimeError(
            f"{stage}: committed master integrity failed after loudnorm — "
            "refuse mark_done (pending/truncated master cannot soft-complete ship)."
        )
    # Done Authority: do not stamp master_finalize here — PMQ is required and is
    # written by run_post_master_quality after this return (SHIP-HOLLOW-FINALIZE).
    ctx.log(
        f"Master render complete — {master_rel} at {target:.1f} LUFS target "
        "(await PMQ before mark_done).",
        level="success",
        stage=stage,
        detail=str(master),
    )
    return master


def _master_filter_chain(
    cfg: dict,
    *,
    target_lufs: float,
    true_peak_dbtp: float,
    measured: dict[str, str] | None = None,
) -> str:
    """Build limiter-before-loudnorm chain with validated FFmpeg parameters."""
    if measured:
        loudnorm = (
            f"loudnorm=I={target_lufs}:TP={true_peak_dbtp}:LRA=11:"
            f"measured_I={measured['input_i']}:"
            f"measured_LRA={measured['input_lra']}:"
            f"measured_TP={measured['input_tp']}:"
            f"measured_thresh={measured['input_thresh']}:"
            f"offset={measured['target_offset']}:"
            # Podcast masters are mono but played on stereo systems — without
            # dual_mono, integrated LUFS reads ~3 LU quiet and fails ship QC.
            "dual_mono=true:linear=true:print_format=summary"
        )
    else:
        loudnorm = (
            f"loudnorm=I={target_lufs}:TP={true_peak_dbtp}:"
            "LRA=11:dual_mono=true:print_format=summary"
        )
    master_cfg = cfg.get("master") if isinstance(cfg.get("master"), dict) else {}
    if not bool(master_cfg.get("safety_limiter_enabled", True)):
        return loudnorm

    limit_db = float(master_cfg.get("safety_limiter_limit_db", -1.0))
    attack_ms = float(master_cfg.get("safety_limiter_attack_ms", 5.0))
    release_ms = float(master_cfg.get("safety_limiter_release_ms", 50.0))
    if not -12.0 <= limit_db <= 0.0:
        raise ValueError("master.safety_limiter_limit_db must be between -12 and 0 dBFS")
    if not 0.1 <= attack_ms <= 80.0:
        raise ValueError("master.safety_limiter_attack_ms must be between 0.1 and 80 ms")
    if not 1.0 <= release_ms <= 8000.0:
        raise ValueError("master.safety_limiter_release_ms must be between 1 and 8000 ms")

    linear_limit = math.pow(10.0, limit_db / 20.0)
    limiter = (
        f"alimiter=limit={linear_limit:.6f}:"
        f"attack={attack_ms:g}:release={release_ms:g}"
    )
    # The pre-loudnorm limiter cannot hold the ship ceiling: loudnorm applies its
    # own (linear) make-up gain *after* it, so a quiet-average / peaky podcast lands
    # above TP. exec_11871 shipped at -0.40 dBTP against a -1.00 ceiling and
    # tools/verify_master.py FAILed. Re-limit after normalization; `level=disabled`
    # keeps alimiter from auto-normalizing the loudness we just set.
    ceiling_linear = math.pow(10.0, float(true_peak_dbtp) / 20.0)
    post_limiter = (
        f"alimiter=limit={ceiling_linear:.6f}:"
        f"attack={attack_ms:g}:release={release_ms:g}:level=disabled"
    )
    return f"{limiter},{loudnorm},{post_limiter}"


def _ffmpeg_loudnorm_probe(assembly: Path, *, target: float, true_peak: float) -> dict[str, str]:
    from interview_mux.operator_subprocess import run_command

    measure = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-y",
            "-i",
            str(assembly),
            "-af",
            f"loudnorm=I={target}:TP={true_peak}:LRA=11:dual_mono=true:print_format=json",
            "-f",
            "null",
            "-",
        ],
        label=f"ffmpeg loudnorm probe {assembly.name}",
        capture_output=True,
    )
    return _extract_loudnorm_json(measure.stderr or "")

def _extract_loudnorm_json(stderr: str) -> dict[str, str]:
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("Could not parse loudnorm metrics from ffmpeg output.")
    data = json.loads(stderr[start : end + 1])
    required = ("input_i", "input_lra", "input_tp", "input_thresh", "target_offset")
    missing = [key for key in required if key not in data]
    if missing:
        missing_keys = ", ".join(missing)
        raise RuntimeError(f"Incomplete loudnorm output from ffmpeg (missing {missing_keys}).")
    return data

def _optimizer_skipped(ctx: RunContext) -> bool:
    """True when the operator (or the unattended driver) answered Skip."""
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    except Exception:
        return False
    return bool(
        isinstance(meta, dict)
        and (meta.get("timeline_optimizer_skipped") or meta.get("timeline_optimizer_cleared"))
    )


def run_master_finalize(ctx: RunContext) -> Path:
    from interview_mux.air_order import assert_consumer
    from interview_mux.gates import require_g_listen_clear, require_timeline_optimizer_clear

    assert_consumer(ctx, "master_finalize")
    # S4: no entry-book heals — PMQ structural checks refuse unpaid omit/hash/VO.

    require_timeline_optimizer_clear(ctx, stage="master_finalize")
    require_g_listen_clear(ctx, stage="master_finalize")
    # S1: refuse unpaid optimizer — never take_best / nest junction here.
    try:
        from interview_mux.order_hash import ordered_segment_ids_hash
        from interview_mux.timeline_optimizer.state import (
            load_best,
            load_optimizer_state,
            save_optimizer_state,
        )

        state = load_optimizer_state(ctx)
        best = load_best(ctx)
        # A best candidate the run's authority refused to promote, or one the
        # operator skipped, is advisory: demanding it here can never be paid
        # (exec_049 sat at 65 of 72, ISSUES entry 53).
        best_waived = bool(state.get("auto_promote_attempted")) or _optimizer_skipped(ctx)
        if (
            best
            and best.get("score") is not None
            and not state.get("finalize_applied_best")
            and not best_waived
        ):
            sel_order = []
            sel = None
            if ctx.artifact_exists("master/selection.json"):
                sel = ctx.read_json("master/selection.json")
                sel_order = [
                    str(s) for s in ((sel or {}).get("ordered_segment_ids") or []) if s
                ]
            best_order = [str(s) for s in (best.get("ordered_segment_ids") or []) if s]
            sel_doc = sel if isinstance(sel, dict) else {}
            best_hash = str(
                best.get("order_hash")
                or best.get("order_content_hash")
                or ordered_segment_ids_hash(best_order)
                or ""
            )
            sel_hash = str(
                sel_doc.get("order_hash")
                or sel_doc.get("order_content_hash")
                or ordered_segment_ids_hash(sel_order)
                or ""
            )
            needs = bool(best_order and best_order != sel_order)
            if (
                best_hash
                and sel_hash
                and best_hash == sel_hash
                and ctx.artifact_exists("master/assembly.wav")
            ):
                needs = False
            if needs or state.get("promoted_needs_remaster"):
                from interview_mux.loud_fail import raise_loud_failure

                raise_loud_failure(
                    ctx,
                    "Timeline optimizer best take is unpaid — apply take-best "
                    "(or remaster) via mix/junction before master_finalize; "
                    "finalize refuses nested remaster.",
                    stage="master_finalize",
                    reason="optimizer_best_unpaid",
                    detail={
                        "promoted_needs_remaster": bool(
                            state.get("promoted_needs_remaster")
                        ),
                        "best_order_len": len(best_order),
                        "selection_order_len": len(sel_order),
                    },
                )
            state = load_optimizer_state(ctx)
            state["finalize_applied_best"] = True
            save_optimizer_state(ctx, state)
    except Exception as exc:
        from interview_mux.loud_fail import LoudStageFailure, raise_loud_failure

        if isinstance(exc, LoudStageFailure):
            raise
        name = type(exc).__name__
        if name == "LoudStageFailure":
            raise
        raise_loud_failure(
            ctx,
            f"Could not verify timeline optimizer seating before finalize: {exc}",
            stage="master_finalize",
            reason="optimizer_best_unpaid",
            cause=exc,
        )
    out = master_wav(ctx, "master/assembly.wav", "master/master.wav", flow="podcast")
    from interview_mux.post_master_quality import run_post_master_quality

    run_post_master_quality(ctx, block=True)
    try:
        from interview_mux.gates import mark_g_publish_pending

        mark_g_publish_pending(ctx)
    except Exception as exc:
        ctx.log(f"g_publish pending mark skipped: {exc}", level="warning", stage="master_finalize")
    return out

