"""Tests for forensics stall guard."""

from __future__ import annotations

from interview_mux.forensics_stall import (
    escalation_blocks_driver,
    predicate_key,
    record_stall,
    write_escalation,
)
from interview_mux.run_context import RunContext


def test_predicate_key_stable_for_same_reason(tmp_path, monkeypatch):
  monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
  ctx = RunContext("test_forensics_stall", create=True)
  a = predicate_key(stage="mix", reason="selection_edl_order_drift: speech clip order diverges")
  b = predicate_key(stage="mix", reason="selection_edl_order_drift: speech clip order diverges")
  assert a == b
  c = predicate_key(stage="junction_snip_qa", reason="selection_edl_order_drift: speech clip order diverges")
  assert a != c


def test_record_stall_escalates_after_three(tmp_path, monkeypatch):
  monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
  ctx = RunContext("test_forensics_stall2", create=True)
  reason = "seed order: complete junction_snip_qa before running master_finalize"
  row1 = record_stall(ctx, stage="junction_snip_qa", reason=reason)
  row2 = record_stall(ctx, stage="junction_snip_qa", reason=reason)
  row3 = record_stall(ctx, stage="junction_snip_qa", reason=reason)
  assert row1["count"] == 1
  assert row2["count"] == 2
  assert row3["count"] == 3
  assert row3["should_escalate"] is True


def test_escalation_blocks_until_product_changes(tmp_path, monkeypatch):
  monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
  ctx = RunContext("test_forensics_stall3", create=True)
  reason = "selection_edl_order_drift"
  row = record_stall(ctx, stage="mix", reason=reason, escalate_after=1)
  write_escalation(ctx, stage="mix", reason=reason, stall_row=row)
  blocked, _ = escalation_blocks_driver(ctx)
  assert blocked is True
  # Simulate product patch by changing fingerprint stored on escalation.
  esc = ctx.read_json("operator/forensics_escalation.json")
  esc["product_fingerprint"] = "patched-fingerprint"
  ctx.write_json("operator/forensics_escalation.json", esc)
  blocked, _ = escalation_blocks_driver(ctx)
  assert blocked is False
