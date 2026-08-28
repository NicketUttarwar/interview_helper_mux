"""Tests for air-order boundary bus lifecycle and checkpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.air_order_boundary import (
    checkpoint_air_order,
    commit_selection_mutation,
    should_block_commit,
)
from interview_mux.air_order_integrity import on_selection_order_changed


class _Ctx:
    def __init__(self, tmp_path: Path):
        self.run_dir = tmp_path
        self._done: set[str] = set()
        self.logs: list[tuple] = []
        self._json: dict[str, dict] = {}

    def final_path(self, *parts: str) -> Path:
        return self.run_dir.joinpath(*parts)

    def path(self, *parts: str) -> Path:
        return self.final_path(*parts)

    def artifact_exists(self, rel: str) -> bool:
        return rel in self._json or self.final_path(*rel.split("/")).is_file()

    def read_json(self, rel: str):
        if rel in self._json:
            return dict(self._json[rel])
        path = self.final_path(*rel.split("/"))
        import json

        return json.loads(path.read_text())

    def write_json(self, rel: str, data, stage_key=None, skip_handoff=False):
        self._json[rel] = dict(data)
        path = self.final_path(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        path.write_text(json.dumps(data))
        return path

    def is_done(self, stage: str) -> bool:
        return stage in self._done or self.final_path(".stage_done", stage).is_file()

    def log(self, msg, level="info", stage=None, detail=None):
        self.logs.append((level, msg))


def _write_starts(ctx: _Ctx, starts: dict[str, int]) -> None:
    ctx.write_json(
        "segments/boundaries.json",
        {
            "boundaries": [
                {"segment_id": sid, "start_ms": ms} for sid, ms in starts.items()
            ]
        },
    )


def test_montage_reorder_bridge_passes_checkpoint(tmp_path: Path) -> None:
    ctx = _Ctx(tmp_path)
    _write_starts(
        ctx,
        {"seg_a": 600_000, "seg_b": 500_000, "seg_c": 700_000},
    )
    ctx.write_json(
        "understanding/reorder_bridges.json",
        {
            "bridges": [
                {"after_segment_id": "seg_a", "before_segment_id": "seg_b"},
            ]
        },
    )
    selection = {"ordered_segment_ids": ["seg_a", "seg_b", "seg_c"]}
    _, result = checkpoint_air_order(
        ctx, selection, producer="full_master_ranking", mode="detect"
    )
    assert not result.critical_remaining


def test_nle_overlay_softens_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _Ctx(tmp_path)
    _write_starts(ctx, {"seg_a": 500_000, "seg_b": 100_000})
    ctx.write_json("operator/nle_edits.json", {"sequence_order": ["seg_b", "seg_a"]})
    selection = {"ordered_segment_ids": ["seg_a", "seg_b"]}

    monkeypatch.setattr(
        "interview_mux.air_order_boundary.nle_overlay_active", lambda _c: True
    )
    _, result = checkpoint_air_order(
        ctx, selection, producer="full_master_ranking", mode="detect"
    )
    assert result.violations
    assert not result.critical_remaining
    assert not should_block_commit(
        result, producer="full_master_ranking", mode="repair"
    )


def test_repair_then_commit_not_blocked(tmp_path: Path) -> None:
    ctx = _Ctx(tmp_path)
    _write_starts(
        ctx,
        {
            "seg_001": 0,
            "seg_003": 152_000,
            "seg_050": 2_416_000,
            "seg_001c": 0,
            "seg_001d": 0,
        },
    )
    selection = {
        "ordered_segment_ids": ["seg_003", "seg_050", "seg_001c", "seg_001d"],
        "excluded_segment_ids": [],
    }
    repaired, result = checkpoint_air_order(
        ctx, selection, producer="full_master_ranking", mode="repair"
    )
    assert not result.critical_remaining
    ordered = repaired.get("ordered_segment_ids") or []
    assert ordered.index("seg_001c") < ordered.index("seg_003")


def test_order_change_clears_transitions_stage_done(tmp_path: Path) -> None:
    ctx = _Ctx(tmp_path)
    prev = {"ordered_segment_ids": ["seg_a", "seg_b"]}
    cur = {"ordered_segment_ids": ["seg_b", "seg_a"]}
    ctx.write_json("master/selection.json", prev)
    done = ctx.final_path(".stage_done", "transitions")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("1")
    notes = on_selection_order_changed(ctx, source="test", previous=prev, current=cur)
    assert "cleared_stage_done:transitions" in notes
    assert not done.is_file()


def test_exclude_only_does_not_invalidate(tmp_path: Path) -> None:
    ctx = _Ctx(tmp_path)
    prev = {
        "ordered_segment_ids": ["seg_a", "seg_b"],
        "excluded_segment_ids": [],
    }
    cur = {
        "ordered_segment_ids": ["seg_a", "seg_b"],
        "excluded_segment_ids": [{"segment_id": "seg_x", "reason": "test"}],
    }
    done = ctx.final_path(".stage_done", "transitions")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("1")
    notes = on_selection_order_changed(ctx, source="test", previous=prev, current=cur)
    assert notes == []
    assert done.is_file()


def test_commit_selection_mutation_detect_producer(tmp_path: Path) -> None:
    ctx = _Ctx(tmp_path)
    _write_starts(ctx, {"seg_a": 0, "seg_b": 60_000})
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_a"]})
    out = commit_selection_mutation(
        ctx,
        {"ordered_segment_ids": ["seg_a", "seg_b"], "excluded_segment_ids": []},
        producer="junction_snip_qa",
        stage_key="junction_snip_qa",
        checkpoint_mode="detect",
        write_committed=True,
    )
    assert out.get("ordered_segment_ids") == ["seg_a", "seg_b"]
