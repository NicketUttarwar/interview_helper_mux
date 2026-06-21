from __future__ import annotations

from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import build_sonic_context


def run_sonic_context_build(ctx: RunContext) -> None:
    with logged_step("sonic_context_build/build", ctx=ctx, stage="sonic_context_build"):
        doc = build_sonic_context(ctx)
        write_validated_artifact(
            ctx,
            "understanding/sonic_context.json",
            doc,
            merge_from_disk=False,
            stage_key="sonic_context_build",
        )
    ctx.log(
        "sonic_context_build: wrote understanding/sonic_context.json",
        level="success",
        stage="sonic_context_build",
        detail={
            "atlas_bucket": ((doc.get("scenario") or {}).get("atlas_bucket")),
            "tag_count": len(doc.get("tag_registry") or []),
            "cue_count": len(doc.get("cue_opportunities") or []),
            "sonic_context_hash": doc.get("sonic_context_hash"),
        },
    )
    ctx.mark_done("sonic_context_build")
