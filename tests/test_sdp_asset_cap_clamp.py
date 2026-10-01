"""The sound design plan never exceeds its asset cap on disk (ISSUES 114)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.sound_design_caps import clamp_assets_to_cap, sound_design_asset_cap
from run_fixtures import isolated_run_ctx


def _brief(ctx, density: dict) -> None:
    # Straight to disk: the cap reader needs only sfx_density, and the schema
    # of a full brief is not the point here.
    import json

    p = ctx.final_path("understanding", "delivery_brief.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"sfx_density": density}), encoding="utf-8")


def _plan(n: int, used: tuple[str, ...]) -> dict:
    return {
        "assets": [{"asset_id": f"a{i}", "role": "bed"} for i in range(1, n + 1)],
        "flow_plans": {
            "podcast": {
                "cues": [{"cue_id": f"c_{a}", "asset_id": a, "segment_id": "seg_1", "description": "bed"} for a in used]
            }
        },
    }


def test_clamp_keeps_cue_referenced_assets_first_and_drops_their_orphans() -> None:
    doc = _plan(8, used=("a8", "a2"))
    out, note = clamp_assets_to_cap(doc, 7)
    ids = [a["asset_id"] for a in out["assets"]]
    assert len(ids) == 7 and "a8" in ids and "a2" in ids
    assert note["dropped_assets"] == ["a7"] and note["dropped_cues"] == 0
    # A dropped asset takes its cues with it.
    out2, note2 = clamp_assets_to_cap(_plan(8, used=("a1", "a8")), 1)
    assert [a["asset_id"] for a in out2["assets"]] == ["a1"]
    assert out2["flow_plans"]["podcast"]["cues"] == [
        {"cue_id": "c_a1", "asset_id": "a1", "segment_id": "seg_1", "description": "bed"}
    ]
    assert note2["dropped_cues"] == 1
    # Within the cap: untouched, no note.
    same, none = clamp_assets_to_cap(_plan(3, used=()), 7)
    assert none is None and len(same["assets"]) == 3
    # Pure.
    assert len(doc["assets"]) == 8


def test_cap_narrows_to_the_delivery_brief_density(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "sdp_cap")
    base = sound_design_asset_cap(ctx)
    assert base >= 1
    _brief(ctx, {"max_beds": 1, "max_punctuators": 1, "max_foley": 0})
    assert sound_design_asset_cap(ctx) == min(base, 2)


def test_sanitizer_applies_the_clamp_so_the_lint_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.artifact_sanitize.sound_design_plan import sanitize_sound_design_plan
    from interview_mux.deterministic_lint import _lint_sound_design_plan

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "sdp_cap_sanitize")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1"]}, skip_handoff=True)
    _brief(ctx, {"max_beds": 1, "max_punctuators": 1, "max_foley": 1})
    cap = sound_design_asset_cap(ctx)
    doc = _plan(cap + 1, used=(f"a{cap + 1}",))
    assert any("exceeds cap" in e for e in _lint_sound_design_plan(doc, ctx))
    res = sanitize_sound_design_plan(ctx, doc)
    assert res.ok
    assert any(a.get("action") == "clamp_assets_to_cap" for a in res.actions)
    assert not any("exceeds cap" in e for e in _lint_sound_design_plan(res.doc, ctx))
    assert any(a["asset_id"] == f"a{cap + 1}" for a in res.doc["assets"])
