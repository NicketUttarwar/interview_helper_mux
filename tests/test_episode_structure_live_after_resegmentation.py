"""Readers get a live episode structure after re-segmentation renumbers ids (ISSUES 172).

exec_022: the connector fuse renumbered segments after episode_structure_compose
ran; gap_framing_compose then paired the stale structure with live text and the
model answered partial ("target contexts are shifted ... seg_021 ... 'Okay.'").
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


def _write(ctx, rel: str, doc: dict) -> None:
    path = ctx.run_dir.joinpath(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "exec_es_live")
    _write(c, "segments/manifest.json", {"segments": [{"segment_id": f"seg_{i:03d}", "start_ms": i * 1000, "end_ms": i * 1000 + 900, "text": "x"} for i in range(1, 6)]})
    return c


def test_stale_structure_is_rebuilt_in_memory(ctx, monkeypatch) -> None:
    from interview_mux import episode_structure as es

    _write(ctx, "understanding/episode_structure.json", {"segment_order": ["seg_001", "seg_007", "seg_009"]})
    monkeypatch.setattr(es, "build_episode_structure", lambda c, refresh=False: {"segment_order": ["seg_001", "seg_002"]})
    live = es.load_episode_structure(ctx)
    assert live["segment_order"] == ["seg_001", "seg_002"]
    assert live["_meta"]["rebuilt_in_memory_from_stale"] is True
    stored = json.loads(ctx.run_dir.joinpath("understanding", "episode_structure.json").read_text())
    assert stored["segment_order"] == ["seg_001", "seg_007", "seg_009"]
    assert es.load_episode_structure(ctx, live=False)["segment_order"] == ["seg_001", "seg_007", "seg_009"]


def test_current_structure_is_returned_as_stored(ctx, monkeypatch) -> None:
    from interview_mux import episode_structure as es

    doc = {"segment_order": ["seg_001", "seg_003"], "slot_plan": [{"bound_segment_ids": ["seg_005"]}]}
    _write(ctx, "understanding/episode_structure.json", doc)
    monkeypatch.setattr(es, "build_episode_structure", lambda *a, **k: pytest.fail("must not rebuild"))
    assert es.load_episode_structure(ctx) == doc


def test_stale_ids_in_slot_plan_count(ctx) -> None:
    from interview_mux.episode_structure import episode_structure_is_stale

    assert episode_structure_is_stale(ctx, {"segment_order": ["seg_001"], "slot_plan": [{"bound_segment_ids": ["seg_040"]}]})
