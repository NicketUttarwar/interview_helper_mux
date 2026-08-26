"""Tests for air-order integrity detection and repair."""

from __future__ import annotations

from interview_mux.air_order_integrity import (
    late_opening_cluster_violations,
    pull_mid_arc_reverse_jumps,
    repair_opening_tape_integrity,
    reverse_tape_jump_violations,
)


def test_reverse_tape_jump_detects_exec_188_shape():
    ordered = ["seg_003", "seg_050", "seg_001c", "seg_001d", "seg_058"]
    starts = {
        "seg_001": 0,
        "seg_003": 152_000,
        "seg_050": 2_416_000,
        "seg_001c": 0,
        "seg_001d": 0,
        "seg_058": 2_500_000,
    }
    violations = reverse_tape_jump_violations(None, ordered, starts=starts)
    assert violations
    assert any(v.get("before_segment_id") == "seg_001c" for v in violations)


def test_pull_mid_arc_drops_opening_cluster_when_guest_first():
    ordered = ["seg_003", "seg_050", "seg_001c", "seg_001d"]
    starts = {"seg_001": 0, "seg_003": 152_000, "seg_050": 2_416_000, "seg_001c": 0, "seg_001d": 0}
    pulled, moved, dropped = pull_mid_arc_reverse_jumps(
        ordered, starts, guest_first=True
    )
    assert "seg_001c" in dropped or "seg_001c" not in pulled
    assert "seg_003" == pulled[0]


def test_late_opening_cluster_violation():
    ordered = ["seg_003", "seg_050", "seg_001c"]
    starts = {"seg_001": 0, "seg_003": 152_000, "seg_050": 2_416_000, "seg_001c": 0}
    violations = late_opening_cluster_violations(None, ordered, starts=starts)
    assert violations


class _FakeCtx:
    def __init__(self, starts: dict[str, int] | None = None):
        self._starts = starts or {}
        self.logs: list[tuple] = []

    def artifact_exists(self, path: str) -> bool:
        return path in {"segments/boundaries.json"}

    def read_json(self, path: str):
        if path == "segments/boundaries.json":
            return {
                "boundaries": [
                    {"segment_id": sid, "start_ms": ms} for sid, ms in self._starts.items()
                ]
            }
        return {}


def test_repair_opening_tape_guest_first_excludes_cluster():
    ctx = _FakeCtx(
        {
            "seg_001": 0,
            "seg_003": 152_000,
            "seg_050": 2_416_000,
            "seg_001c": 0,
            "seg_001d": 0,
        }
    )
    selection = {
        "ordered_segment_ids": ["seg_003", "seg_050", "seg_001c", "seg_001d"],
        "excluded_segment_ids": [],
    }
    repaired, actions = repair_opening_tape_integrity(ctx, selection)
    ordered = repaired.get("ordered_segment_ids") or []
    assert "seg_001c" not in ordered
    assert "seg_001d" not in ordered
    excl = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in (repaired.get("excluded_segment_ids") or [])
    }
    assert "seg_001c" in excl
    assert actions
