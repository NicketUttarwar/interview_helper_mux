from __future__ import annotations

from interview_mux.artifact_completeness import compute_gaps
from interview_mux.llm_shard_plans import DECOMPOSE_ELIGIBLE, should_proactive_decompose_content_context
from interview_mux.pipeline import ANALYSIS_ORDER
from interview_mux.prompt_validation import validate_content_brief
from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_manifest_segment


def test_analysis_order_includes_content_brief_reanchor():
    seg_idx = ANALYSIS_ORDER.index("segment_classification")
    reanchor_idx = ANALYSIS_ORDER.index("content_brief_reanchor")
    sonic_idx = ANALYSIS_ORDER.index("sonic_context_build")
    pal_idx = ANALYSIS_ORDER.index("sound_design_palettes")
    assert reanchor_idx == seg_idx + 1
    assert sonic_idx == reanchor_idx + 1
    assert pal_idx == sonic_idx + 1


def test_decompose_eligible_includes_content_brief_reanchor():
    assert "content_brief_reanchor" in DECOMPOSE_ELIGIBLE


def test_proactive_decompose_when_transcript_exceeds_threshold():
    long_text = "x" * 80000
    assert should_proactive_decompose_content_context({"transcript": long_text}) is True
    assert should_proactive_decompose_content_context({"transcript": "short"}) is False


def test_enriched_content_brief_schema_valid():
    brief = minimal_content_brief(
        key_claims=[
            {
                "id": "claim_001",
                "claim": "A supported claim.",
                "claim_type": "fact",
                "segment_ids": ["seg_001"],
                "evidence_segment_ids": ["seg_001"],
                "depends_on_claim_ids": [],
            }
        ],
        topic_relationships=[
            {
                "from_topic": "Topic A",
                "to_topic": "Topic B",
                "relation": "supports",
                "description": "B backs up A",
                "evidence_segment_ids": ["seg_002"],
            }
        ],
    )
    assert validate_content_brief(brief) == []


def test_reanchor_gap_rules_require_segment_ids_and_relationships():
    brief = minimal_content_brief(
        topics=[{"name": "Topic A", "summary": "Summary.", "segment_ids": []}],
        topic_relationships=[],
    )
    gaps = compute_gaps(
        "understanding/content_brief.json",
        brief,
        stage_key="content_brief_reanchor",
    )
    paths = {g.path for g in gaps}
    assert "topics[0].segment_ids" in paths
    assert "topic_relationships" in paths


def test_content_brief_reanchor_build_input(tmp_path, monkeypatch):
    from interview_mux.stages import understanding

    ctx = isolated_run_ctx(tmp_path, "run_reanchor_input")
    ctx.write_json(
        "understanding/content_brief.json",
        minimal_content_brief(thesis="Test thesis"),
    )
    ctx.write_json(
        "segments/manifest.json",
        {"segments": [minimal_manifest_segment(segment_id="seg_001")]},
    )
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {
                    "speaker_id": "spk_001",
                    "role": "interviewer",
                    "confidence": 0.9,
                    "evidence": ["asks questions"],
                }
            ]
        },
    )
    ctx.write_json(
        "segments/boundaries.json",
        {
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "proposed_split_reason": "pause",
                }
            ]
        },
    )

    captured: dict = {}

    def fake_run(_ctx, stage_key, _prompt, build_input, *_args, **_kwargs):
        captured["payload"] = build_input(_ctx)
        captured["stage_key"] = stage_key

    monkeypatch.setattr(understanding, "run_analysis_llm_stage", fake_run)
    understanding.run_content_brief_reanchor(ctx)
    assert captured["stage_key"] == "content_brief_reanchor"
    assert "content_brief" in captured["payload"]
    assert "segments" in captured["payload"]
