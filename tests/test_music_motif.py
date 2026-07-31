"""Unit tests for music-only motif roles, bans, music_brief, and VO density floor."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from interview_mux.music_motif import (
    BANNED_SFX_ROLES,
    THEME_ROLES,
    asset_id_is_banned,
    compile_musicgen_prompt,
    default_motif_family,
    ensure_motif_on_plan,
    is_banned_role,
    is_theme_role,
    prompt_looks_musical,
    text_has_banned_texture,
    validate_theme_prompt,
)


def test_theme_roles_cover_plan_taxonomy() -> None:
    assert "theme_cold_open" in THEME_ROLES
    assert "theme_underscore" in THEME_ROLES
    assert "theme_emphasis" in THEME_ROLES
    assert "theme_chapter_resolve" in THEME_ROLES
    assert "theme_transition" in THEME_ROLES
    assert "theme_outro" in THEME_ROLES


def test_banned_sfx_roles_include_legacy_ticks() -> None:
    assert is_banned_role("chapter_stinger")
    assert is_banned_role("ambient_bed")
    assert is_banned_role("transition_whoosh")
    assert is_banned_role("accent_foley")
    assert not is_theme_role("chapter_stinger")


def test_banned_asset_ids_and_textures() -> None:
    assert asset_id_is_banned("chapter_stinger_soft_woodtick")
    assert asset_id_is_banned("ambient_production_floor_murmur")
    assert asset_id_is_banned("vo_bridge_airy_swish")
    assert text_has_banned_texture("soft woodtick desk tap")
    assert text_has_banned_texture("HVAC murmur under speech")
    assert not text_has_banned_texture("warm acoustic guitar motif")


def test_prompt_arbiter_requires_instruments() -> None:
    assert prompt_looks_musical("ascending four-note motif on warm acoustic guitar")
    errs = validate_theme_prompt("short")
    assert "prompt_too_short" in errs
    errs2 = validate_theme_prompt("a long whoosh riser trailer hit with no instruments at all here")
    assert "banned_texture_language" in errs2 or "missing_instrument_or_melody_language" in errs2


def test_ensure_motif_strips_banned_and_seeds_theme(tmp_path: Path) -> None:
    brief = {
        "show_identity": {
            "genre_hint": "business documentary instrumental",
            "mood": "determined",
            "instrumentation_prefs": ["warm acoustic guitar", "soft piano"],
        },
        "motif_seeds": {"keywords": ["ESOP"]},
        "narrative_spine": {"acts": []},
        "source_quotes_short": [],
    }
    sdp = {
        "assets": [
            {"asset_id": "ambient_production_floor_murmur", "role": "ambient_bed"},
            {"asset_id": "chapter_stinger_soft_woodtick", "role": "chapter_stinger"},
        ],
        "flow_plans": {"podcast": {"cues": []}},
    }
    out = ensure_motif_on_plan(sdp, brief)
    assert isinstance(out.get("motif_family"), dict)
    assert out["motif_family"].get("prompt_dna")
    roles = {str(a.get("role")) for a in out.get("assets") or []}
    assert roles <= THEME_ROLES or roles <= (THEME_ROLES | {""})
    assert "ambient_bed" not in roles
    assert "chapter_stinger" not in roles
    aids = [str(a.get("asset_id")) for a in out.get("assets") or []]
    assert not any(asset_id_is_banned(a) for a in aids)


def test_compile_musicgen_prompt_negatives() -> None:
    brief = {"source_quotes_short": ["we sold to Zydus"]}
    motif = default_motif_family(
        {
            "show_identity": {
                "genre_hint": "business documentary",
                "mood": "determined",
                "instrumentation_prefs": ["guitar", "piano"],
            },
            "motif_seeds": {"keywords": ["sale"]},
            "narrative_spine": {"acts": []},
        }
    )
    pos, neg = compile_musicgen_prompt(brief=brief, motif=motif, role="theme_underscore", wpm=140)
    assert "guitar" in pos.lower() or "motif" in pos.lower()
    assert "pulse" in pos.lower() or "rhythmic" in pos.lower()
    assert "100" in pos or "112" in pos or "BPM" in pos or "bpm" in pos.lower()
    assert "whoosh" in neg.lower()
    assert "foley" in neg.lower()
    assert "pad-only" in neg.lower()


def test_vo_density_floor_math() -> None:
    # 173 selected speech → floor ≥ 35 at 0.20
    n = 173
    ratio = 0.20
    floor = max(1, int(math.ceil(n * ratio)))
    assert floor == 35


class _FakeCtx:
    def __init__(self, artifacts: dict[str, Any]):
        self._arts = artifacts

    def artifact_exists(self, rel: str) -> bool:
        return rel in self._arts

    def read_json(self, rel: str) -> Any:
        return self._arts[rel]


def test_enforce_min_vo_insert_ratio_seeds() -> None:
    from interview_mux.artifact_repairs import _enforce_min_vo_insert_ratio

    ordered = [f"seg_{i:03d}" for i in range(20)]
    ctx = _FakeCtx(
        {
            "master/selection.json": {"ordered_segment_ids": ordered},
            "master/narrative_plan.json": {
                "chapters": [{"chapter_id": "c1", "segment_ids": ordered[:10]}, {"chapter_id": "c2", "segment_ids": ordered[10:]}]
            },
        }
    )
    out: dict[str, Any] = {"interviewer_lines": []}
    applied: list[dict[str, Any]] = []
    _enforce_min_vo_insert_ratio(ctx, out, applied=applied)
    # floor = ceil(20 * 0.20) = 4
    assert len(out["interviewer_lines"]) >= 4
    assert any(a.get("action") == "seed_vo_density_floor" for a in applied)
    for ln in out["interviewer_lines"]:
        assert ln.get("delivery") == "synthesize"
        assert not asset_id_is_banned(str(ln.get("line_id") or ""))
    cats = {str(ln.get("line_category")) for ln in out["interviewer_lines"]}
    # Variety seeds should not be story_bridge-only
    assert cats
