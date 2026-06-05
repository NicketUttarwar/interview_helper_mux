from __future__ import annotations

from interview_mux.show_description_qc import validate_show_description
from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_manifest, minimal_manifest_segment


def test_show_description_qc_requires_evidence_ids(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_sdqc")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
    )
    errors = validate_show_description(
        ctx,
        {
            "description_markdown": "A" * 400,
            "word_count": 150,
            "hook_sentence": "Hook here.",
            "themes_highlighted": ["theme"],
            "audience_pitch": "pitch",
            "tone": "journalistic",
            "confidence": 0.8,
            "evidence_segment_ids": [],
        },
    )
    assert any("evidence_segment_ids" in e for e in errors)


def test_show_description_qc_passes_with_valid_evidence(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_sdqc_ok")
    body = "Hook here. " + ("word " * 148)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
    )
    ctx.write_json(
        "understanding/content_brief.json",
        minimal_content_brief(
            key_claims=[{"claim": "growth strategy"}],
        ),
    )
    errors = validate_show_description(
        ctx,
        {
            "description_markdown": body,
            "word_count": 150,
            "hook_sentence": "Hook here.",
            "themes_highlighted": ["growth strategy"],
            "audience_pitch": "pitch",
            "tone": "journalistic",
            "confidence": 0.9,
            "evidence_segment_ids": ["seg_001"],
        },
    )
    assert errors == []
