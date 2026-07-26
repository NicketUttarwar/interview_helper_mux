"""Palette keyword provenance alignment with sonic_context."""

from __future__ import annotations

from interview_mux.deterministic_lint import deterministic_lint
from interview_mux.sonic_context import (
    align_palette_keywords_to_sonic_context,
    build_palette_keyword_catalog,
    palette_keyword_matches_sonic_provenance,
    sonic_provenance_keyword_set,
)


def test_palette_keyword_matches_substring_and_tokens():
    sonic = {"early life and return to india", "decision to sell and choosing zydus wellness"}
    assert palette_keyword_matches_sonic_provenance("early life", sonic)
    assert palette_keyword_matches_sonic_provenance("return", sonic)
    assert palette_keyword_matches_sonic_provenance("village", sonic) is False


def test_build_palette_keyword_catalog_from_registry():
    doc = {
        "tag_registry": [
            {
                "tag_id": "topic_early_life",
                "kind": "topic",
                "keywords": ["Early life and return to India"],
                "segment_ids": ["seg_008"],
                "provenance": ["content_brief.topics"],
            }
        ]
    }
    catalog = build_palette_keyword_catalog(doc)
    assert len(catalog) == 1
    assert catalog[0]["tag_id"] == "topic_early_life"
    assert "Early life and return to India" in catalog[0]["keywords"]


def test_align_palette_keywords_from_segment_overlap():
    sonic = {
        "tag_registry": [
            {
                "tag_id": "topic_early_life",
                "kind": "topic",
                "keywords": ["Early life and return to India", "early_life_and_return_to_india"],
                "segment_ids": ["seg_008", "seg_009"],
            }
        ]
    }
    palettes = [
        {
            "palette_id": "village_roots_intro",
            "theme_label": "Rural Origins",
            "keywords": ["village", "early life"],
            "segment_ids": ["seg_008", "seg_009"],
        }
    ]
    aligned = align_palette_keywords_to_sonic_context(palettes, sonic)
    assert any(
        palette_keyword_matches_sonic_provenance(k, sonic_provenance_keyword_set(sonic))
        for k in aligned[0]["keywords"]
    )


def test_lint_sound_design_palettes_accepts_aligned_keywords(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from interview_mux.run_context import RunContext

    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setenv("INTERVIEW_MUX_RUN_DIR", str(run))
    ctx = RunContext(str(run), create=True)
    sonic_fixture = (
        Path(__file__).resolve().parent / "fixtures" / "sonic_context" / "fireside.json"
    )
    sonic = json.loads(sonic_fixture.read_text(encoding="utf-8"))
    sonic["tag_registry"] = [
        {
            "tag_id": "topic_early_life",
            "kind": "topic",
            "keywords": ["Early life and return to India"],
            "segment_ids": ["seg_001"],
            "provenance": ["content_brief.topics"],
        }
    ]
    ctx.write_json("understanding/sonic_context.json", sonic, skip_handoff=True)
    from run_fixtures import minimal_manifest

    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"))
    artifacts = {
        "coherence": {"sonic_identity": "Warm documentary intimacy under speech.", "density": "sparse"},
        "palettes": [
            {
                "palette_id": "early_life",
                "theme_label": "Early life",
                "keywords": ["early life"],
                "segment_ids": ["seg_001"],
                "tag_ids": ["topic_early_life"],
            }
        ],
    }
    errors = deterministic_lint("sound_design_palettes", {"artifacts": artifacts}, ctx)
    assert not any("provenance" in e for e in errors)
