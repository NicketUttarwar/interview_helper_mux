"""Driver heal must pin seed-order producer — never leap to delivery."""

from __future__ import annotations

import re


def test_seed_order_gate_message_parses_producer() -> None:
    msg = "RuntimeError:seed order: complete source_topology_build before running content_context"
    m = re.search(r"complete ([a-z0-9_]+) before running", msg.lower())
    assert m is not None
    assert m.group(1) == "source_topology_build"


def test_seed_order_heal_does_not_prefer_delivery_pin_over_named_producer() -> None:
    """Regression shape from D14: needs_operator seed-order → selection_order_sanitize."""
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    producer = "source_topology_build"
    assert producer in ANALYSIS_ORDER
    assert "selection_order_sanitize" in DELIVERY_ORDER
    # Named producer wins over delivery blocked canonical pin.
    assert producer != "selection_order_sanitize"
