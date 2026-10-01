"""A duplicated asset row never reaches the plan on disk or trips the prompt count (ISSUES 122)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.sound_design_caps import dedupe_assets
from run_fixtures import isolated_run_ctx


def test_dedupe_keeps_the_first_row_per_asset_id() -> None:
    doc = {
        "assets": [
            {"asset_id": "a", "role": "theme_cold_open"},
            {"asset_id": "b", "role": "theme_outro", "description": "first"},
            {"asset_id": "b", "role": "theme_outro", "description": "second"},
            {"asset_id": "c", "role": "theme_emphasis"},
        ]
    }
    out, note = dedupe_assets(doc)
    assert [a["asset_id"] for a in out["assets"]] == ["a", "b", "c"]
    assert out["assets"][1]["description"] == "first"
    assert note == {"action": "dedupe_assets", "dropped_duplicates": ["b"]}
    assert len(doc["assets"]) == 4
    same, none = dedupe_assets({"assets": [{"asset_id": "a"}]})
    assert none is None and len(same["assets"]) == 1


def test_sanitizer_drops_the_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.artifact_sanitize.sound_design_plan import sanitize_sound_design_plan

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "sdp_dupe")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1"]}, skip_handoff=True)
    doc = {
        "assets": [
            {"asset_id": "motif", "role": "theme_cold_open"},
            {"asset_id": "close", "role": "theme_outro"},
            {"asset_id": "close", "role": "theme_outro"},
        ],
        "flow_plans": {"podcast": {"cues": []}},
    }
    res = sanitize_sound_design_plan(ctx, doc)
    assert res.ok
    assert [a["asset_id"] for a in res.doc["assets"]] == ["motif", "close"]
    assert any(a.get("action") == "dedupe_assets" for a in res.actions)


def test_prompt_count_is_judged_against_distinct_asset_ids() -> None:
    import interview_mux.sdp_cross_validate as m

    src = Path(m.__file__).read_text(encoding="utf-8")
    assert "len(rows) < len(assets_by_id)" in src
    assert "len(rows) < len(assets):" not in src
