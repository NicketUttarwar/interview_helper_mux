"""Endless mid-mix timeline optimizer — per-run search for a beautiful master.

Mode C: daemon keeps permuting after a shippable mix exists.
Mutation surface 4: structure + glue + SDP + optional LLM Shape/ranking proposals.
"""

from __future__ import annotations

from interview_mux.timeline_optimizer.config import optimizer_cfg
from interview_mux.timeline_optimizer.daemon import (
    is_optimizer_running,
    start_optimizer_daemon,
    stop_optimizer_daemon,
)
from interview_mux.timeline_optimizer.state import (
    load_optimizer_state,
    optimizer_status_payload,
)
from interview_mux.timeline_optimizer.apply import take_best_candidate

__all__ = [
    "optimizer_cfg",
    "is_optimizer_running",
    "start_optimizer_daemon",
    "stop_optimizer_daemon",
    "load_optimizer_state",
    "optimizer_status_payload",
    "take_best_candidate",
]
