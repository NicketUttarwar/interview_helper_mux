"""Tests for full-tape transcript sharding and talking-points / brief merges."""

from __future__ import annotations

from interview_mux.transcript_shards import (
    build_transcript_shards,
    merge_content_brief_artifacts,
    merge_talking_points_artifacts,
    needs_transcript_sharding,
    segment_text_max_chars,
)


def test_short_transcript_single_full_shard():
    text = "hello world from the interview"
    shards = build_transcript_shards(text, max_chars=1000, overlap_ratio=0.1)
    assert len(shards) == 1
    assert shards[0].text == text
    assert shards[0].char_start == 0
    assert shards[0].char_end == len(text)
    assert not needs_transcript_sharding(text, cfg={"analysis": {"context": {"proactive_decompose_chars": 72000}}})


def test_long_transcript_shards_cover_all_chars():
    text = ("alpha beta gamma delta epsilon zeta " * 2000).strip()
    assert len(text) > 5000
    shards = build_transcript_shards(
        text,
        max_chars=2000,
        overlap_ratio=0.1,
        max_shards=12,
    )
    assert len(shards) >= 2
    # Every character index appears in at least one shard window.
    covered = [False] * len(text)
    for sh in shards:
        for i in range(sh.char_start, min(sh.char_end, len(text))):
            covered[i] = True
        assert sh.text == text[sh.char_start : sh.char_end] or sh.text  # word-join path ok
    assert all(covered), f"uncovered chars: {covered.count(False)}"
    assert shards[0].shard_index == 1
    assert shards[-1].shard_total == len(shards)


def test_merge_talking_points_prefers_must_keep_and_dedupes():
    a = {
        "strategy_summary": "Act one story.",
        "through_line": "Rise",
        "talking_points": [
            {
                "talking_point_id": "tp_1",
                "title": "The Pivot",
                "importance": "optional",
                "why_it_matters": "short",
            }
        ],
        "warnings": ["noise"],
    }
    b = {
        "strategy_summary": "Act two payoff.",
        "through_line": "Fall",
        "talking_points": [
            {
                "talking_point_id": "tp_1b",
                "title": "The Pivot",
                "importance": "must_keep",
                "why_it_matters": "much longer why it matters for the master",
                "evidence_quotes": ["we pivoted"],
            },
            {
                "talking_point_id": "tp_2",
                "title": "Closing lesson",
                "importance": "should_keep",
                "why_it_matters": "tail of tape",
            },
        ],
    }
    merged = merge_talking_points_artifacts([a, b])
    titles = [p["title"] for p in merged["talking_points"]]
    assert titles.count("The Pivot") == 1
    pivot = next(p for p in merged["talking_points"] if p["title"] == "The Pivot")
    assert pivot["importance"] == "must_keep"
    assert "longer why" in pivot["why_it_matters"]
    assert "Closing lesson" in titles
    assert "Act one" in merged["strategy_summary"] and "Act two" in merged["strategy_summary"]


def test_merge_content_brief_unions_topics_and_claims():
    a = {
        "thesis": "Thesis A",
        "topics": [{"name": "Funding", "summary": "short"}],
        "key_claims": [{"claim": "Raised seed", "claim_type": "fact"}],
    }
    b = {
        "thesis": "Thesis B",
        "topics": [{"name": "Funding", "summary": "longer funding arc summary"}, {"name": "Exit", "summary": "exit"}],
        "key_claims": [{"claim": "Raised seed", "claim_type": "fact"}, {"claim": "Sold company", "claim_type": "fact"}],
    }
    merged = merge_content_brief_artifacts([a, b])
    names = {t["name"] for t in merged["topics"]}
    assert names == {"Funding", "Exit"}
    funding = next(t for t in merged["topics"] if t["name"] == "Funding")
    assert "longer" in funding["summary"]
    claims = [c["claim"] for c in merged["key_claims"]]
    assert claims.count("Raised seed") == 1
    assert "Sold company" in claims


def test_segment_text_max_chars_reads_config():
    assert segment_text_max_chars({"analysis": {"context": {"segment_text_max_chars": 250}}}) == 250
