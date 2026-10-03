"""A keeper trim on a fused slab must not reach the source segmentation (ISSUES 142).

exec_007: a fused 2271-2948 s slab was clamped in the manifest to its ideal-cut
keeper window from 2818 s. The next fuse round copied every surviving manifest
row's times into segments/boundaries.json, nine minutes of speech fell out of the
source map, coverage dropped to 0.84, and every delivery stage refused it as
unsafe cuts until the run stopped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


def _row(sid: str, start: int, end: int, **extra) -> dict:
    row = {
        "segment_id": sid,
        "start_ms": start,
        "end_ms": end,
        "proposed_split_reason": "topic_shift",
        "speaker_id": "spk_1",
        "speaker_role": "interviewee",
        "type": "interviewee_answer",
        "topic_tags": [],
        "text": "It changes how we treat them.",
    }
    row.update(extra)
    return row


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "exec_fuse_spans")
    dest = c.final_path("segments", "boundaries.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(
            {
                "boundaries": [
                    _row("seg_001", 0, 100_000),
                    # A slab an earlier round fused: its source row spans the union.
                    _row("seg_002", 100_000, 400_000, fused_from=["seg_002", "seg_003"]),
                    _row("seg_004", 400_000, 450_000),
                    _row("seg_005", 450_000, 500_000),
                ]
            }
        ),
        encoding="utf-8",
    )
    return c


def _bounds(ctx) -> dict[str, tuple[int, int]]:
    doc = json.loads(ctx.final_path("segments", "boundaries.json").read_text(encoding="utf-8"))
    return {r["segment_id"]: (r["start_ms"], r["end_ms"]) for r in doc["boundaries"]}


def test_next_fuse_round_keeps_the_trimmed_slab_source_span(ctx) -> None:
    from interview_mux.segment_fuse import _write_boundaries

    surviving = [
        _row("seg_001", 0, 100_000),
        # Manifest row clamped to its keeper window by rerun_air_bounds_on_fused.
        _row("seg_002", 340_000, 400_000, fused_from=["seg_002", "seg_003"]),
        # This round fuses seg_005 into seg_004.
        _row("seg_004", 400_000, 500_000, fused_from=["seg_004", "seg_005"]),
    ]
    _write_boundaries(ctx, surviving, consumed={"seg_005"}, pass_id="post_sanitize")
    b = _bounds(ctx)
    assert b["seg_002"] == (100_000, 400_000)
    assert b["seg_004"] == (400_000, 500_000)
    assert "seg_005" not in b


def test_unfused_rows_keep_their_source_times(ctx) -> None:
    from interview_mux.segment_fuse import _write_boundaries

    surviving = [
        _row("seg_001", 20_000, 90_000),
        _row("seg_002", 100_000, 400_000, fused_from=["seg_002", "seg_003"]),
        _row("seg_004", 400_000, 450_000),
        _row("seg_005", 450_000, 500_000),
    ]
    _write_boundaries(ctx, surviving, consumed=set(), pass_id="post_sanitize")
    assert _bounds(ctx)["seg_001"] == (0, 100_000)
