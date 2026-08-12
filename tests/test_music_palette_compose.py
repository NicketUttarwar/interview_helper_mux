"""Fixed music palette counts, compose reuse, MusicGen ladder, soft duration."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from interview_mux.music_motif import (
    analysis_palette_counts,
    build_fixed_palette_assets,
    compile_musicgen_prompt,
    default_motif_family,
    ensure_motif_on_plan,
    harden_palette_inventory,
    palette_kind_for_role,
)
from interview_mux.music_lane import LANE_BED, LANE_BOOKEND, LANE_PUNCTUATOR, music_lane_for_role
from interview_mux.musicgen_runner import clamp_music_duration
from interview_mux.stages.music_palette_compose import _apply_cues, _default_cues


class _FakeCtx:
    def __init__(self, artifacts: dict[str, Any]):
        self._arts = artifacts

    def artifact_exists(self, rel: str) -> bool:
        return rel in self._arts

    def read_json(self, rel: str) -> Any:
        return self._arts[rel]


def test_analysis_palette_counts_sparse_vs_dense() -> None:
    sparse = _FakeCtx(
        {
            "mastering/mastering_plan.json": {
                "confirmed_mode": "conversational_host",
                "narrative_mode": "conversational_host",
            },
            "master/narrative_plan.json": {"chapters": [{"title": "a"}, {"title": "b"}]},
            "master/selection.json": {"ordered_segment_ids": ["s1", "s2", "s3"]},
            "understanding/soundscape_policy.json": {
                "sfx_density": {"max_beds": 1, "max_punctuators": 2},
                "cue_slots": [],
            },
        }
    )
    sc = analysis_palette_counts(sparse)  # type: ignore[arg-type]
    assert sc["motif"] == 1
    assert sc["underscore_loop"] == 1
    assert sc["optional_loop"] == 0
    assert sc["full_beds"] == 1
    assert sc["stingers"] <= 2

    dense = _FakeCtx(
        {
            "mastering/mastering_plan.json": {
                "confirmed_mode": "hook_montage",
                "narrative_mode": "hook_montage",
            },
            "master/narrative_plan.json": {
                "chapters": [{"title": f"c{i}"} for i in range(4)]
            },
            "master/selection.json": {
                "ordered_segment_ids": [f"s{i}" for i in range(12)]
            },
            "understanding/soundscape_policy.json": {
                "sfx_density": {"max_beds": 3, "max_punctuators": 6},
                "cue_slots": [],
            },
        }
    )
    dc = analysis_palette_counts(dense)  # type: ignore[arg-type]
    assert dc["optional_loop"] == 1
    assert dc["full_beds"] == 2
    assert dc["stingers"] >= 3


def test_harden_palette_exact_inventory() -> None:
    brief = {
        "show_identity": {
            "genre_hint": "doc",
            "mood": "determined",
            "instrumentation_prefs": ["guitar", "piano", "bass"],
        },
        "motif_seeds": {"keywords": ["x"]},
        "narrative_spine": {"acts": []},
    }
    counts = {
        "motif": 1,
        "underscore_loop": 1,
        "optional_loop": 0,
        "stingers": 2,
        "full_beds": 1,
    }
    out = harden_palette_inventory({"assets": [], "flow_plans": {}}, brief, counts=counts)
    kinds = [str(a.get("palette_kind")) for a in out["assets"]]
    assert kinds.count("motif") == 1
    assert kinds.count("underscore_loop") == 1
    assert kinds.count("optional_loop") == 0
    assert kinds.count("stinger") == 2
    assert kinds.count("full_bed") == 1
    assert len(out["assets"]) == 5


def test_compose_cues_reuse_palette_only() -> None:
    brief = {
        "show_identity": {
            "genre_hint": "doc",
            "mood": "determined",
            "instrumentation_prefs": ["guitar", "piano"],
        },
        "motif_seeds": {"keywords": []},
        "narrative_spine": {"acts": []},
    }
    assets = build_fixed_palette_assets(
        brief,
        {
            "motif": 1,
            "underscore_loop": 1,
            "optional_loop": 1,
            "stingers": 2,
            "full_beds": 2,
        },
    )
    sdp = {"assets": assets, "flow_plans": {"podcast": {"cues": []}}}
    ordered = ["seg_a", "seg_b", "seg_c", "seg_d"]
    chapters = [
        {"title": "one", "segment_ids": ["seg_a", "seg_b"]},
        {"title": "two", "segment_ids": ["seg_c", "seg_d"]},
    ]
    cues = _default_cues(sdp, ordered=ordered, chapters=chapters)
    known = {str(a["asset_id"]) for a in assets}
    assert cues
    assert all(str(c["asset_id"]) in known for c in cues)
    bed_ids = [
        c["asset_id"]
        for c in cues
        if c.get("placement") == "under_segment"
    ]
    # Alternation when optional exists
    if len(bed_ids) >= 2:
        assert len(set(bed_ids)) >= 1
    applied = _apply_cues(sdp, cues + [{"asset_id": "not_in_palette", "placement": "under_segment"}])
    podcast = applied["flow_plans"]["podcast"]
    assert all(str(c["asset_id"]) in known for c in podcast["cues"])
    assert podcast.get("composed_by") == "music_palette_compose"


def test_compile_musicgen_prompt_is_succinct() -> None:
    motif = default_motif_family(
        {
            "show_identity": {
                "genre_hint": "business documentary",
                "mood": "determined",
                "instrumentation_prefs": ["guitar", "piano", "bass", "strings"],
            },
            "motif_seeds": {"keywords": ["sale"]},
            "narrative_spine": {"acts": []},
        }
    )
    pos, neg = compile_musicgen_prompt(
        brief={},
        motif=motif,
        role="theme_underscore",
        palette_kind="underscore_loop",
        wpm=140,
    )
    assert len(pos.split()) <= 80
    assert "guitar" in pos.lower() or "piano" in pos.lower()
    assert "vocals" in neg.lower()
    assert "whoosh" in neg.lower()


def test_clamp_music_duration_no_hard_ceiling() -> None:
    # Full beds may stretch past soft advisory max.
    long = clamp_music_duration(30.0, role="theme_cold_open")
    assert long >= 30.0
    short = clamp_music_duration(1.0, role="theme_underscore")
    assert short >= 4.0


def test_mix_lanes_for_palette_kinds() -> None:
    assert music_lane_for_role("motif") == LANE_BOOKEND
    assert music_lane_for_role("full_bed") == LANE_BOOKEND
    assert music_lane_for_role("underscore_loop") == LANE_BED
    assert music_lane_for_role("optional_loop") == LANE_BED
    assert music_lane_for_role("stinger") == LANE_PUNCTUATOR
    assert palette_kind_for_role("theme_underscore", energy="lift") == "optional_loop"


def test_musicgen_ladder_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import json
    import subprocess

    import interview_mux.musicgen_runner as mg

    monkeypatch.setattr(mg, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(mg, "e2e_musicgen_fast_stub", lambda: False)
    monkeypatch.setattr(mg, "musicgen_venv_python", lambda: tmp_path / "python")
    (tmp_path / "python").write_text("#!/bin/sh\n")
    monkeypatch.setattr(
        mg,
        "musicgen_cfg",
        lambda: {
            "device": "cpu",
            "ban_mps_on_abort": True,
            "request_timeout_sec": 5,
            "step_down_timeout_sec": 5,
            "prefer_medium_on_cpu": False,
            "model_id": "facebook/musicgen-large",
            "min_duration_sec": 4.0,
            "mmaudio_backup_on_stub": True,
        },
    )
    monkeypatch.setattr(mg, "cli_python_executable", lambda p: p)
    monkeypatch.setattr(mg, "effective_musicgen_device", lambda **kwargs: "cpu")
    hub = tmp_path / "hf_cache" / "hub"
    for mid in ("facebook/musicgen-medium", "facebook/musicgen-small"):
        (hub / ("models--" + mid.replace("/", "--"))).mkdir(parents=True)
    monkeypatch.setattr(mg, "musicgen_hf_home", lambda: tmp_path / "hf_cache")

    class _DummyLock:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def acquire(self, *args, **kwargs) -> bool:  # noqa: ANN002, ANN003
            return True

        def release(self) -> None:
            pass

    import filelock

    monkeypatch.setattr(filelock, "FileLock", _DummyLock)
    models: list[str] = []

    def fake_spawn(**kwargs):  # noqa: ANN003
        req = Path(str(kwargs["req"]))
        payload = json.loads(req.read_text())
        models.append(str(payload.get("model_id")))
        return subprocess.CompletedProcess(kwargs["py"], 1, "", "fail")

    monkeypatch.setattr(mg, "_spawn_musicgen", fake_spawn)
    # generate_music_clip checks tools/musicgen_generate.py under repo root — ensure path exists via real repo.
    out = tmp_path / "bed.wav"
    meta = mg.generate_music_clip(
        prompt="guitar piano bass motif",
        negative_prompt="vocals",
        duration_sec=12.0,
        out_wav=out,
        role="theme_underscore",
        seed=1,
    )
    assert meta.get("backend") == "musical_stub"
    assert models, "expected MusicGen ladder attempts"
    assert models[0].endswith("large")
    assert any(m.endswith("medium") for m in models)
    assert any(m.endswith("small") for m in models)
    assert (meta.get("model_ladder") or [])[0].endswith("large")


def test_ensure_motif_with_counts() -> None:
    brief = {
        "show_identity": {
            "genre_hint": "doc",
            "mood": "hopeful",
            "instrumentation_prefs": ["guitar", "piano"],
        },
        "motif_seeds": {"keywords": []},
        "narrative_spine": {"acts": []},
    }
    out = ensure_motif_on_plan(
        {"assets": [], "flow_plans": {}},
        brief,
        counts={"motif": 1, "underscore_loop": 1, "optional_loop": 1, "stingers": 1, "full_beds": 2},
    )
    kinds = [a.get("palette_kind") for a in out["assets"]]
    assert kinds.count("optional_loop") == 1
    assert kinds.count("full_bed") == 2
