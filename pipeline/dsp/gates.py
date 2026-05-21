from __future__ import annotations

from typing import Any


def require_dsp_gate(
    conn: Any,
    tool_name: str,
    *,
    run_id: str | None = None,
    approve: bool = False,
) -> None:
    """
    High-risk first-use gate for preset E tools (pedalboard, demucs, etc.).
    Set approve=True once operator accepts risk.
    """
    from mux_store import append_event, execution_kv_get, execution_kv_set

    key = f"dsp_gate.approved.{tool_name}"
    if execution_kv_get(conn, key):
        return
    if approve:
        execution_kv_set(conn, key, {"approved": True})
        return
    if run_id:
        append_event(
            conn,
            run_id,
            severity="warning",
            kind="gate",
            message=f"DSP tool '{tool_name}' blocked until approved. Re-run with --approve-dsp.",
        )
    raise RuntimeError(
        f"DSP gate: '{tool_name}' not approved. Run with --approve-dsp after reading "
        "docs/execution/high-risk-first-use-gating.md"
    )
