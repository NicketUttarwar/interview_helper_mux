"""Tests for air-order integrity detection and repair."""

from __future__ import annotations

from run_fixtures import mark_done_raw
from interview_mux.air_order_integrity import (
    critical_violations,
    late_opening_cluster_violations,
    pull_mid_arc_reverse_jumps,
    repair_air_order_integrity,
    repair_opening_tape_integrity,
    reverse_tape_jump_violations,
    write_air_order_integrity_report,
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


def test_repair_opening_tape_guest_first_prepends_host_not_last_late_family():
    """Multiple opening families: prepend earliest host, not the last late cluster."""
    ctx = _FakeCtx(
        {
            "seg_002": 26_119,
            "seg_003": 83_780,
            "seg_003ca": 97_970,
            "seg_004": 124_840,
            "seg_005": 151_600,
            "seg_007": 168_310,
            "seg_008": 185_780,
        }
    )
    selection = {
        "ordered_segment_ids": [
            "seg_007",
            "seg_005",
            "seg_004",
            "seg_002",
            "seg_003ca",
            "seg_008",
        ],
        "excluded_segment_ids": [],
    }
    before = late_opening_cluster_violations(
        ctx, selection["ordered_segment_ids"]
    )
    assert len(before) >= 2
    repaired, actions = repair_opening_tape_integrity(ctx, selection)
    ordered = [str(s) for s in (repaired.get("ordered_segment_ids") or [])]
    assert ordered[0] == "seg_002"
    assert "seg_007" in ordered
    assert "seg_003ca" in ordered
    assert not late_opening_cluster_violations(ctx, ordered)
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


def test_exec_805_letter_split_family_passes():
    """Eight seg_001 letter-splits + seg_002 + seg_003 should not trip family slot cap."""
    ordered = [
        "seg_001c",
        "seg_001d",
        "seg_001e",
        "seg_001f",
        "seg_001h",
        "seg_001i",
        "seg_001j",
        "seg_001k",
        "seg_002",
        "seg_003",
        "seg_006",
    ]
    starts = {
        "seg_001": 0,
        "seg_002": 124_840,
        "seg_003": 151_660,
        "seg_006": 200_000,
    }
    policy = {
        "opening_window_ms": 180_000,
        "opening_air_slots": 6,
        "count_opening_by_family": True,
    }
    violations = late_opening_cluster_violations(
        None, ordered, starts=starts, policy=policy
    )
    assert not critical_violations(violations)


def test_late_opening_still_flags_true_late_cluster():
    ordered = ["seg_003", "seg_050", "seg_001c"]
    starts = {"seg_001": 0, "seg_003": 152_000, "seg_050": 2_416_000, "seg_001c": 0}
    policy = {"opening_window_ms": 180_000, "opening_air_slots": 6, "count_opening_by_family": True}
    violations = late_opening_cluster_violations(
        None, ordered, starts=starts, policy=policy
    )
    assert violations


def test_resolved_policy_in_report(tmp_path):
    class _Ctx:
        def __init__(self):
            self.run_dir = tmp_path
            self.logs: list[tuple] = []

        def write_json(self, rel, doc, stage_key=None):
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            import json

            path.write_text(json.dumps(doc), encoding="utf-8")

        def path(self, *parts):
            p = tmp_path.joinpath(*parts)
            p.parent.mkdir(parents=True, exist_ok=True)
            return p

        def log(self, message, level="info", stage=None, detail=None):
            self.logs.append((message, level, stage))

        def artifact_exists(self, path: str) -> bool:
            return False

    ctx = _Ctx()
    policy = {
        "source_duration_ms": 3_600_000,
        "opening_air_slots": 6,
        "count_opening_by_family": True,
    }
    doc = write_air_order_integrity_report(
        ctx,
        violations=[],
        stage="test",
        resolved_policy=policy,
    )
    assert doc.get("resolved_policy") == policy


def test_junction_source_skips_layup_invalidate(tmp_path, monkeypatch):
    """Junction remaster must not archive mix via layup invalidate."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.run_context import RunContext
    from interview_mux.air_order_integrity import on_selection_order_changed

    ctx = RunContext(create=True)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_a", "seg_b"], "order_lock": {"revision": 1}},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {"ordered_segment_ids": ["seg_a", "seg_b"], "layups": []},
        skip_handoff=True,
    )
    mark_done_raw(ctx, "nugget_layup_compose")
    calls: list[str] = []

    def _fake_invalidate(_ctx, stage: str) -> None:
        calls.append(stage)

    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.invalidate_downstream",
        _fake_invalidate,
    )
    notes = on_selection_order_changed(
        ctx,
        source="junction_snip_qa",
        previous={"ordered_segment_ids": ["seg_a", "seg_b", "seg_c"]},
        current={"ordered_segment_ids": ["seg_a", "seg_b"]},
    )
    assert "skipped_layup_invalidate:junction_source" in notes
    assert calls == []
    notes2 = on_selection_order_changed(
        ctx,
        source="full_master_ranking",
        previous={"ordered_segment_ids": ["seg_a", "seg_b", "seg_c"]},
        current={"ordered_segment_ids": ["seg_a", "seg_b"]},
    )
    assert "invalidated_downstream:nugget_layup_compose" in notes2
    assert calls == ["nugget_layup_compose"]
