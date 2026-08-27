"""Tests for air-order integrity detection and repair."""

from __future__ import annotations

from interview_mux.air_order_integrity import (
    late_opening_cluster_violations,
    pull_mid_arc_reverse_jumps,
    repair_air_order_integrity,
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


def test_pull_mid_arc_prepends_opening_cluster_when_guest_first():
    """Prefer native host intro: prepend opening-window family, do not drop."""
    ordered = ["seg_003", "seg_050", "seg_001c", "seg_001d"]
    starts = {
        "seg_001": 0,
        "seg_003": 152_000,
        "seg_050": 2_416_000,
        "seg_001c": 0,
        "seg_001d": 0,
    }
    pulled, moved, dropped = pull_mid_arc_reverse_jumps(
        ordered, starts, guest_first=True
    )
    assert not dropped
    assert "seg_001c" in pulled
    # Mid-arc prepends before the reverse-jump pair; opening-tape repair
    # then moves the family to episode front.
    assert pulled.index("seg_001c") < pulled.index("seg_050")
    assert moved


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


def test_repair_opening_tape_guest_first_prepends_cluster():
    """Default mode prepends host-intro family instead of opening_skipped_duplicate."""
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
    assert "seg_001c" in ordered
    assert "seg_001d" in ordered
    assert ordered.index("seg_001c") < ordered.index("seg_003")
    excl = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in (repaired.get("excluded_segment_ids") or [])
    }
    assert "seg_001c" not in excl
    assert any(a.get("action") == "prepend_opening_family" for a in actions)


def test_repair_opening_tape_drop_override_still_excludes():
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
    repaired, actions = repair_opening_tape_integrity(
        ctx, selection, mode="drop_if_guest_first"
    )
    ordered = repaired.get("ordered_segment_ids") or []
    assert "seg_001c" not in ordered
    excl = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in (repaired.get("excluded_segment_ids") or [])
    }
    assert "seg_001c" in excl
    assert actions


def test_repair_air_order_prefers_host_intro_over_company_pitch():
    """Host intro + company pitch both stay; host intro lands first."""
    ctx = _FakeCtx(
        {
            "seg_002": 26_000,
            "seg_003": 49_000,
            "seg_003b": 51_000,
            "seg_008": 200_000,
        }
    )
    selection = {
        "ordered_segment_ids": ["seg_003b", "seg_008", "seg_002"],
        "excluded_segment_ids": [
            {"segment_id": "seg_002", "reason": "opening_skipped_duplicate"},
        ],
        "exclude_rationales": {"seg_002": "opening_skipped_duplicate"},
    }
    repaired, actions = repair_air_order_integrity(ctx, selection)
    ordered = [str(x) for x in (repaired.get("ordered_segment_ids") or [])]
    assert "seg_002" in ordered
    assert "seg_003b" in ordered
    assert ordered.index("seg_002") < ordered.index("seg_003b")
    excl = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in (repaired.get("excluded_segment_ids") or [])
    }
    assert "seg_002" not in excl
    assert (repaired.get("exclude_rationales") or {}).get("seg_002") != (
        "opening_skipped_duplicate"
    )
    assert actions
