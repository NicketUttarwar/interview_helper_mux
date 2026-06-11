from __future__ import annotations

from pathlib import Path

from interview_mux.run_context import RunContext


def run_mix_flow2(ctx: RunContext) -> Path:
    """Flow 2 highlight montage mix (canonical stage id)."""
    from interview_mux.llm_flow_hardening import require_spend_artifacts_complete
    from interview_mux.sound_design import mix_flow2

    require_spend_artifacts_complete(ctx, "mix_flow2")
    return mix_flow2(ctx)


def run_micro_assembly(ctx: RunContext) -> Path:
    """Backward-compatible alias for mix_flow2 (v1 pipeline stage id)."""
    assembly = run_mix_flow2(ctx)
    ctx.mark_done("mux_flow2")
    return assembly
