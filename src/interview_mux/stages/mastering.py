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
    ctx.mark_done(stage)
    ctx.log(
        f"Master complete — {master_rel} at {target:.1f} LUFS target.",
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
    return f"{limiter},{loudnorm}"


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

def run_master_finalize(ctx: RunContext) -> Path:
    from interview_mux.air_order import assert_consumer
    from interview_mux.gates import require_g_listen_clear, require_timeline_optimizer_clear
    from interview_mux.omit_ledger import heal_omit_ledger_air_contract
    from interview_mux.vo_synthesis_audit import sync_edl_vo_script_metadata

    assert_consumer(ctx, "master_finalize")
    # Layup VO in the EDL must have gap-report script authority before PMQ.
    try:
        from interview_mux.nugget_layup import ensure_layup_gap_authority

        ensure_layup_gap_authority(ctx)
    except Exception:
        pass
    # VO text/WAV may have been repaired after EDL build; refresh clip hashes first
    # so post-master audible_script_hash_agreement judges current authority.
    heal = heal_omit_ledger_air_contract(ctx)
    if heal.get("healed"):
        ctx.log(
            "master_finalize: omit-ledger air-contract heal "
            + "; ".join(str(n) for n in (heal.get("notes") or [])),
            level="info",
            stage="master_finalize",
        )
    sync_edl_vo_script_metadata(ctx)

    require_timeline_optimizer_clear(ctx, stage="master_finalize")
    require_g_listen_clear(ctx, stage="master_finalize")
    # The best optimizer take is always applied.  E2E/soft flags cannot bypass
    # this quality decision, and a failed take-best remaster is a hard stop.
    optimizer_applied = False
    try:
        from interview_mux.timeline_optimizer.state import load_best, load_optimizer_state, save_optimizer_state
        from interview_mux.timeline_optimizer.apply import take_best_candidate

        state = load_optimizer_state(ctx)
        best = load_best(ctx)
        if best and best.get("score") is not None and not state.get("finalize_applied_best"):
            sel_order = []
            if ctx.artifact_exists("master/selection.json"):
                sel = ctx.read_json("master/selection.json")
                sel_order = [str(s) for s in ((sel or {}).get("ordered_segment_ids") or []) if s]
            best_order = [str(s) for s in (best.get("ordered_segment_ids") or []) if s]
            from interview_mux.order_hash import ordered_segment_ids_hash

            sel_doc = sel if ctx.artifact_exists("master/selection.json") else {}
            if not isinstance(sel_doc, dict):
                sel_doc = {}
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
            needs = best_order and best_order != sel_order
            if (
                best_hash
                and sel_hash
                and best_hash == sel_hash
                and ctx.artifact_exists("master/assembly.wav")
            ):
                needs = False
            if needs or state.get("promoted_needs_remaster"):
                take_best_candidate(ctx, remaster=True, sync_remaster=True, runner=None)
                optimizer_applied = True
            state = load_optimizer_state(ctx)
            state["finalize_applied_best"] = True
            save_optimizer_state(ctx, state)
    except Exception as exc:
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            f"Could not auto-apply the best timeline optimizer take: {exc}",
            stage="master_finalize",
            reason="optimizer_best_apply_failed",
            cause=exc,
        )
    if optimizer_applied:
        # Optimizer promotion changes final construction authority.  Re-run the
        # complete seam commitment layer before creating the master.
        from interview_mux.junction_snip_qa import run_junction_snip_qa

        run_junction_snip_qa(ctx)
    out = master_wav(ctx, "master/assembly.wav", "master/master.wav", flow="podcast")
    from interview_mux.post_master_quality import run_post_master_quality

    run_post_master_quality(ctx, block=True)
    try:
        from interview_mux.gates import mark_g_publish_pending

        mark_g_publish_pending(ctx)
    except Exception as exc:
        ctx.log(f"g_publish pending mark skipped: {exc}", level="warning", stage="master_finalize")
    return out

