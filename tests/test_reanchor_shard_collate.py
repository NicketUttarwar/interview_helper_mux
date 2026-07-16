from __future__ import annotations

from interview_mux.content_brief_collate import merge_shard_content_brief
from interview_mux.deterministic_lint import deterministic_lint
from interview_mux.llm_shard_plans import build_deterministic_shard_plan
from interview_mux.llm_subtasks import run_shards_then_collate
from interview_mux.topic_tag_bootstrap import bootstrap_manifest_topic_tags
from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_manifest_segment, patch_merged_config


def _segments(n: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        row = minimal_manifest_segment(segment_id=f"seg_{i:03d}")
        row["start_ms"] = (i - 1) * 7000
        row["end_ms"] = i * 7000
        row["text"] = f"segment {i} protein bar stevia funding zydus"
        rows.append(row)
    return rows


def test_reanchor_shard_plan_covers_all_forty_segments():
    stage_input = {
        "content_brief": minimal_content_brief(),
        "segments": {"segments": _segments(40)},
    }
    plan, source = build_deterministic_shard_plan(
        "content_brief_reanchor",
        stage_input,
        truncation_flags=["lint_retry_force_decompose"],
    )
    assert source == "deterministic"
    assert len(plan) <= 12
    covered = {sid for shard in plan for sid in shard.get("segment_ids") or []}
    assert len(covered) == 40
    assert covered == {f"seg_{i:03d}" for i in range(1, 41)}


def test_run_shards_then_collate_uses_config_cap_not_eight(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_shard_cap")
    patch_merged_config(
        monkeypatch,
        {"analysis": {"context": {"max_shard_batches": 12, "max_transcript_shards": 12}}},
    )
    plan = [{"label": f"seg_{i:03d}", "segment_ids": [f"seg_{i:03d}"]} for i in range(1, 13)]
    seen: dict[str, int] = {}

    def fake_shard_envelope(stage_key, prompt_rel, **kwargs):
        task = kwargs.get("task_kind", "primary")
        if task == "shard":
            seen["count"] = seen.get("count", 0) + 1
            sid = plan[seen["count"] - 1]["segment_ids"][0]
            return {
                "status": "complete",
                "artifacts": {
                    "thesis": "T",
                    "topics": [
                        {
                            "name": "Topic A",
                            "summary": "s",
                            "segment_ids": [sid],
                        }
                    ],
                    "topic_relationships": [],
                    "key_claims": [],
                },
                "needs": [],
            }
        return {
            "status": "complete",
            "artifacts": {
                "thesis": "T",
                "topics": [{"name": "Topic A", "summary": "s", "segment_ids": ["seg_001"]}],
                "topic_relationships": [],
                "key_claims": [],
            },
            "needs": [],
        }

    monkeypatch.setattr("interview_mux.llm_subtasks.run_prompt_envelope", fake_shard_envelope)
    monkeypatch.setattr("interview_mux.llm_subtasks.prepare_volley_for_llm", lambda *_a, **_k: ([], None))

    env, count = run_shards_then_collate(
        ctx,
        stage_key="content_brief_reanchor",
        prompt_rel="understanding/content-brief-reanchor.system.txt",
        stage_input={"segments": {"segments": _segments(12)}},
        shard_plan=plan,
    )
    assert count == 12
    assert seen.get("count") == 12
    topics = (env.get("artifacts") or {}).get("topics") or []
    seg_ids = topics[0].get("segment_ids") or []
    assert len(seg_ids) >= 12


def test_merge_shard_content_brief_unions_segment_ids():
    baseline = minimal_content_brief(
        topics=[{"name": "Topic A", "summary": "s", "segment_ids": ["seg_001"]}],
        topic_relationships=[],
    )
    shard_outputs = [
        {
            "label": "a",
            "envelope": {
                "artifacts": {
                    "topics": [{"name": "Topic A", "summary": "s", "segment_ids": ["seg_002"]}],
                    "key_claims": [],
                    "topic_relationships": [],
                }
            },
        },
        {
            "label": "b",
            "envelope": {
                "artifacts": {
                    "topics": [{"name": "Topic A", "summary": "s", "segment_ids": ["seg_010"]}],
                    "key_claims": [],
                    "topic_relationships": [],
                }
            },
        },
    ]
    merged = merge_shard_content_brief(
        {"status": "complete", "artifacts": {}},
        shard_outputs,
        baseline_brief=baseline,
        valid_segment_ids={f"seg_{i:03d}" for i in range(1, 11)},
    )
    topics = merged["artifacts"]["topics"]
    assert set(topics[0]["segment_ids"]) == {"seg_001", "seg_002", "seg_010"}


def test_bootstrap_manifest_topic_tags_from_brief(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_bootstrap")
    brief = minimal_content_brief(
        topics=[
            {
                "name": "Successful pivot to protein bars",
                "summary": "Protein bars traction.",
                "approx_time_range": "00:00-00:14",
                "segment_ids": [],
            }
        ]
    )
    seg = minimal_manifest_segment("seg_001")
    seg["start_ms"] = 0
    seg["end_ms"] = 12000
    seg["text"] = "Naturell shifted focus to protein bars for gym goers"
    seg["topic_tags"] = []
    ctx.write_json("understanding/content_brief.json", brief)
    ctx.write_json("segments/manifest.json", {"segments": [seg]})
    applied = bootstrap_manifest_topic_tags(ctx)
    assert applied == 1
    manifest = ctx.read_json("segments/manifest.json")
    assert manifest["segments"][0]["topic_tags"]


def test_reanchor_coverage_lint_allows_majority_with_tags(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "flow_hardening": {"enabled": False},
                "context": {"content_brief_reanchor_min_coverage_ratio": 0.55},
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "run_cov")
    segs = _segments(10)
    for i, seg in enumerate(segs):
        if i < 6:
            seg["topic_tags"] = ["topic_a"]
    ctx.write_json("segments/manifest.json", {"segments": segs})
    envelope = {
        "status": "complete",
        "confidence": 0.9,
        "artifacts": {
            "thesis": "Example thesis with enough length.",
            "topics": [
                {
                    "name": "Topic A",
                    "summary": "Summary text.",
                    "segment_ids": [f"seg_{i:03d}" for i in range(1, 7)],
                }
            ],
            "topic_relationships": [
                {
                    "from_topic": "Topic A",
                    "to_topic": "Topic A",
                    "relation": "supports",
                    "evidence_segment_ids": ["seg_001"],
                }
            ],
            "key_claims": [],
        },
    }
    errors = deterministic_lint("content_brief_reanchor", envelope, ctx)
    assert not any("segment_coverage_ratio" in e for e in errors)
