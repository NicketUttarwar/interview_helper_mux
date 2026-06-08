from __future__ import annotations

from interview_mux.analysis_memory import (
    ensure_analysis_workspace,
    load_analysis_state,
    sync_content_brief_reanchor_to_state,
    sync_content_brief_to_state,
)
from run_fixtures import isolated_run_ctx


def test_sync_content_brief_preserves_segment_ids(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_sync_brief")
    ensure_analysis_workspace(ctx)
    sync_content_brief_to_state(
        ctx,
        {
            "thesis": "Main point.",
            "topics": [
                {
                    "name": "Topic A",
                    "summary": "About A.",
                    "segment_ids": ["seg_001"],
                }
            ],
            "topic_relationships": [
                {
                    "from_topic": "Topic A",
                    "to_topic": "Topic B",
                    "relation": "supports",
                    "evidence_segment_ids": ["seg_002"],
                }
            ],
            "key_claims": [
                {
                    "id": "claim_001",
                    "claim": "Claim text",
                    "claim_type": "fact",
                    "segment_ids": ["seg_003"],
                }
            ],
        },
    )
    state = load_analysis_state(ctx)
    assert state["themes"][0]["segment_ids"] == ["seg_001"]
    assert state["narrative"]["topic_relationships"][0]["relation"] == "supports"
    assert state["narrative"]["key_claims"][0]["claim_type"] == "fact"


def test_sync_content_brief_reanchor_updates_theme_segments(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_sync_reanchor")
    ensure_analysis_workspace(ctx)
    sync_content_brief_to_state(
        ctx,
        {
            "thesis": "Main point.",
            "topics": [{"name": "Topic A", "summary": "About A.", "segment_ids": []}],
        },
    )
    sync_content_brief_reanchor_to_state(
        ctx,
        {
            "topics": [{"name": "Topic A", "segment_ids": ["seg_010", "seg_011"]}],
            "topic_relationships": [
                {
                    "from_topic": "Topic A",
                    "to_topic": "Topic B",
                    "relation": "prerequisite",
                    "evidence_segment_ids": ["seg_010"],
                }
            ],
        },
    )
    state = load_analysis_state(ctx)
    theme = next(t for t in state["themes"] if t.get("label") == "Topic A")
    assert theme["segment_ids"] == ["seg_010", "seg_011"]
    assert "content_brief_reanchor" in theme["sources"]
    assert state["narrative"]["topic_relationships"][0]["relation"] == "prerequisite"
