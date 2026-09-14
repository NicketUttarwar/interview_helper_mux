"""Pipeline stages for low-confidence island selection + connector seam fuse."""

from __future__ import annotations

from typing import Any

from interview_mux.low_conf_islands import (
    compute_density_ranking,
    low_conf_selection_cfg,
)
from interview_mux.low_conf_islands import (
    run_low_conf_island_scan as scan_low_conf_islands_for_ctx,
)
from interview_mux.low_conf_islands import (
    write_low_conf_must_keep,
)
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.segment_fuse import connector_fuse_cfg
from interview_mux.segment_fuse import fuse_writer_stage
from interview_mux.segment_fuse import run_connector_fuse_pass as fuse_pass

DEFAULT_FUSE_PASS_ID = "post_sanitize"


def _heal_island_stage(ctx: RunContext, stage: str) -> None:
    """HS-1: stamp done only through heal_or_refuse after a real write."""
    from interview_mux.homunculus.agenda import stage_outputs_present
    from interview_mux.stage_completion import heal_or_refuse_mark

    if not stage_outputs_present(ctx, stage):
        return
    heal_or_refuse_mark(ctx, stage, force=True)


def run_low_conf_island_scan(ctx: RunContext) -> None:
    """Scan the low-conf ladder, density-rank natives, publish the top-decile must_keep."""
    stage = "low_conf_island_scan"
    conf = low_conf_selection_cfg()
    if not conf.get("enabled", True):
        ctx.log(
            "low_conf_island_scan skipped (analysis.low_conf_selection.enabled=false)",
            stage=stage,
            action_id="low_conf.scan.skip",
        )
        return

    with logged_step(f"{stage}/scan", ctx=ctx, stage=stage):
        islands = scan_low_conf_islands_for_ctx(ctx)
        ranking = compute_density_ranking(ctx, islands)
        hv_doc: dict[str, Any] = {"island_count": 0, "segment_ids_touched": []}
        try:
            from interview_mux.high_value_speech_islands import (
                mark_segments_high_value,
                scan_high_value_speech_islands,
            )

            hv_doc = scan_high_value_speech_islands(ctx, low_conf_islands=islands)
            mark_segments_high_value(
                ctx, set(hv_doc.get("segment_ids_touched") or [])
            )
        except Exception as exc:
            ctx.log(
                f"high_value_speech_islands scan failed open: {exc}",
                level="warning",
                stage=stage,
                action_id="high_value.scan.fail_open",
            )
        must_keep = write_low_conf_must_keep(ctx, ranking)

    ctx.log(
        f"Low-conf islands: {islands.get('island_count')} found "
        f"({islands.get('suspect_count')} suspect) — "
        f"{len(must_keep.get('must_keep_segment_ids') or [])} segment(s) hard-included "
        f"at top {must_keep.get('top_percentile')}; "
        f"high_value={hv_doc.get('island_count')}",
        stage=stage,
        action_id="low_conf.scan",
        detail={
            "island_count": islands.get("island_count"),
            "tier_counts": islands.get("tier_counts") or {},
            "positive_count": ranking.get("positive_count"),
            "must_keep": (must_keep.get("must_keep_segment_ids") or [])[:20],
            "enforcement_mode": must_keep.get("enforcement_mode"),
            "high_value_count": hv_doc.get("island_count"),
            "high_value_segments": (hv_doc.get("segment_ids_touched") or [])[:20],
        },
    )
    _heal_island_stage(ctx, stage)


def run_connector_fuse_pass(ctx: RunContext, **kwargs: Any) -> None:
    """Economy-LLM seam adjudication + fuse rewrite for one pass."""
    stage = "connector_fuse_pass"
    pass_id = str(kwargs.get("pass_id") or DEFAULT_FUSE_PASS_ID)
    conf = connector_fuse_cfg()
    if not conf.get("enabled", True):
        ctx.log(
            "connector_fuse_pass skipped (analysis.connector_fuse.enabled=false)",
            stage=stage,
            action_id="connector_fuse.skip",
            detail={"pass_id": pass_id},
        )

    with logged_step(f"{stage}/{pass_id}", ctx=ctx, stage=stage):
        result = fuse_pass(
            ctx,
            pass_id=pass_id,
            force_readjudicate=bool(kwargs.get("force_readjudicate")),
        )

    ctx.log(
        f"Connector fuse pass '{pass_id}' complete — {result.get('total_applied')} fuse(s), "
        f"fixed_point={result.get('fixed_point')}, "
        f"hv_cluster={((result.get('high_value_cluster_fuse') or {}).get('total_applied'))}",
        stage=stage,
        action_id="connector_fuse.complete",
        detail={
            "pass_id": pass_id,
            "total_applied": result.get("total_applied"),
            "rounds": len(result.get("rounds") or []),
            "hv_cluster": result.get("high_value_cluster_fuse"),
            "skip_reason": result.get("skip_reason"),
        },
    )
    _heal_island_stage(ctx, fuse_writer_stage(pass_id))


def run_connector_fuse_pass_pre_ranking(ctx: RunContext) -> None:
    """Second fuse pass immediately before full_master_ranking."""
    run_connector_fuse_pass(ctx, pass_id="pre_ranking")


def run_connector_fuse_pass_junction_heal(ctx: RunContext) -> None:
    """Fuse pass scheduled from junction QA when incomplete residuals survive."""
    try:
        asm = ctx.final_path("master", "assembly.wav")
        if asm.is_file() and asm.stat().st_size > 0:
            from interview_mux.timeline_reopen_meta_gate import (
                INTENT_FUSE,
                decide_timeline_reopen,
            )

            gate = decide_timeline_reopen(
                ctx,
                intent=INTENT_FUSE,
                detail={"from_stage": "connector_fuse_pass", "pass_id": "junction_heal"},
            )
            if not gate.get("allow"):
                ctx.log(
                    f"connector fuse junction_heal refused: {gate.get('refuse_reason')}",
                    level="info",
                    stage="connector_fuse_pass",
                )
                return
    except Exception as exc:
        ctx.log(
            f"connector fuse junction_heal fail-closed refuse: {exc}",
            level="info",
            stage="connector_fuse_pass",
        )
        return
    run_connector_fuse_pass(ctx, pass_id="junction_heal", force_readjudicate=True)


__all__ = [
    "DEFAULT_FUSE_PASS_ID",
    "run_connector_fuse_pass",
    "run_connector_fuse_pass_junction_heal",
    "run_connector_fuse_pass_pre_ranking",
    "run_low_conf_island_scan",
]
