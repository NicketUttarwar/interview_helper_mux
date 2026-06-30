from __future__ import annotations

import pytest

from interview_mux.llm_output_resilience import (
    artifact_mass_score,
    resolve_persist_plan,
    sanitize_artifacts,
    upstream_artifact_acceptable,
)
from interview_mux.llm_flow_hardening import (
    complete_llm_stage_or_halt,
    llm_stage_progress_ok,
    require_llm_stage_progress,
)
from interview_mux.llm_stage_routing import finalize_stage_attempt
from run_fixtures import isolated_run_ctx, patch_merged_config


def _minimal_content_brief(**extra: object) -> dict:
    base = {
        "thesis": "Partial thesis",
        "topics": [{"name": "Tech", "summary": "Topic summary", "approx_time_range": "0:00-2:00"}],
    }
    base.update(extra)
    return base


def _minimal_speakers(**extra: object) -> dict:
    base = {
        "speakers": [
            {
                "speaker_id": "spk_1",
                "role": "interviewer",
                "label": "Host",
                "confidence": 0.9,
            }
        ],
    }
    base.update(extra)
    return base


def _resilience_cfg() -> dict:
    return {
        "analysis": {
            "flow_hardening": {"enabled": True, "strict_critical_stages": True},
            "llm_resilience": {
                "progression_mode": "degraded_continue",
                "partial_persist_enabled": True,
                "record_stripped_fields": True,
                "min_artifact_mass": {
                    "content_context": ["thesis"],
                    "speaker_roles": ["speakers"],
                },
            },
            "llm_null_policy": {
                "enabled": True,
                "hard_stop_on_critical_null": True,
            },
        }
    }


def test_sanitize_strips_unanchored_claims(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "sanitize_claims")
    artifacts = {
        "thesis": "Main point",
        "topics": [{"name": "Tech", "approx_time_range": "0:00-2:00"}],
        "key_claims": [
            {
                "id": "c1",
                "claim": "Grounded",
                "approx_time_range": "0:00-1:00",
                "segment_ids": ["seg_001"],
            },
            {"id": "c2", "claim": "No anchor"},
        ],
    }
    sanitized, report = sanitize_artifacts(
        ctx,
        "content_context",
        artifacts,
        lint_errors=["key_claim without evidence anchor"],
    )
    assert len(sanitized["key_claims"]) == 1
    assert sanitized["key_claims"][0]["id"] == "c1"
    assert len(report.stripped) == 1
    assert report.stripped[0]["path"] == "key_claims[1]"


def test_resolve_persist_plan_partial_on_lint(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "persist_partial")
    envelope = {
        "status": "complete",
        "artifacts": {
            "thesis": "Main point",
            "topics": [
                {
                    "name": "Tech",
                    "summary": "Topic summary",
                    "approx_time_range": "0:00-2:00",
                }
            ],
            "key_claims": [{"id": "c2", "claim": "No anchor"}],
        },
    }
    plan = resolve_persist_plan(
        ctx,
        "content_context",
        envelope,
        {"verdict": "accept"},
        [],
        ["key_claim without evidence anchor"],
        cfg=_resilience_cfg(),
    )
    assert plan.action == "partial"
    assert plan.merge_memory is False
    assert "thesis" in plan.artifacts
    assert len(plan.artifacts.get("key_claims") or []) == 0


def test_resolve_persist_plan_full_when_clean(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "persist_full")
    envelope = {
        "status": "complete",
        "artifacts": {
            "thesis": "Main point",
            "topics": [{"name": "Tech", "approx_time_range": "0:00-2:00"}],
        },
    }
    plan = resolve_persist_plan(
        ctx,
        "content_context",
        envelope,
        {"verdict": "accept"},
        [],
        [],
        cfg=_resilience_cfg(),
    )
    assert plan.action == "full"
    assert plan.merge_memory is True


def test_upstream_artifact_acceptable_requires_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _resilience_cfg())
    ctx = isolated_run_ctx(tmp_path, "res_upstream")
    ctx.write_json(
        "understanding/content_brief.json",
        _minimal_content_brief(_meta={"resilience": {"partial": True}}),
        skip_handoff=True,
    )
    assert not upstream_artifact_acceptable(
        "content_context",
        "understanding/content_brief.json",
        ctx,
    )


def test_apply_resilience_critical_null_blocks(tmp_path, monkeypatch):
    from interview_mux.llm_output_resilience import apply_resilience_and_persist

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _resilience_cfg())
    ctx = isolated_run_ctx(tmp_path, "res_critical_null")
    envelope = {
        "status": "complete",
        "artifacts": {
            "thesis": None,
            "topics": [{"name": "Tech", "summary": "Topic summary"}],
        },
        "_llm_meta": {"model_id": "gpt-test", "task_kind": "primary"},
    }
    plan = apply_resilience_and_persist(
        ctx,
        "content_context",
        1,
        envelope,
        {"verdict": "accept"},
        [],
        [],
        persist_fn=lambda _c, _a: None,
    )
    assert plan.action == "none"
    assert envelope.get("status") == "blocked"


def test_finalize_stage_attempt_partial_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _resilience_cfg())
    ctx = isolated_run_ctx(tmp_path, "res_finalize")

    def persist(_ctx, _artifacts):
        return None

    envelope = {
        "status": "complete",
            "artifacts": {
                "thesis": "Saved thesis",
                "topics": [
                    {
                        "name": "Tech",
                        "summary": "Topic summary",
                        "approx_time_range": "0:00-2:00",
                    }
                ],
                "key_claims": [{"id": "c2", "claim": "No anchor"}],
            },
        "_routing_meta": {
            "deterministic_lint_errors": ["key_claim without evidence anchor"],
            "routed_via_collate": False,
        },
    }
    finalize_stage_attempt(
        ctx,
        "content_context",
        1,
        envelope,
        [],
        {"verdict": "accept"},
        [],
        0,
        persist_artifacts=persist,
    )
    assert ctx.artifact_exists("understanding/content_brief.json")
    brief = ctx.read_json("understanding/content_brief.json")
    assert brief["thesis"] == "Saved thesis"
    assert (brief.get("_meta") or {}).get("resilience", {}).get("partial") is True


def test_complete_llm_stage_or_halt_strict_blocks_partial(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _resilience_cfg())
    ctx = isolated_run_ctx(tmp_path, "res_strict")
    ctx.write_json(
        "understanding/content_brief.json",
        _minimal_content_brief(
            thesis="Partial thesis",
            _meta={"resilience": {"partial": True, "summary": "stripped claims"}},
        ),
        skip_handoff=True,
    )
    envelope = {
        "status": "blocked",
        "needs": [],
        "_routing_meta": {
            "persist_action": "partial",
            "resilience_report": {"summary": "stripped claims", "stripped": [], "generated": []},
        },
    }
    with pytest.raises(SystemExit, match="LLM stage gate"):
        complete_llm_stage_or_halt(
            ctx,
            "content_context",
            envelope,
            schema_errors=["minor"],
            cfg=_resilience_cfg(),
        )
    assert not ctx.is_done("content_context")


def test_require_llm_stage_progress_rejects_partial_upstream(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _resilience_cfg())
    ctx = isolated_run_ctx(tmp_path, "res_upstream_prog")
    ctx.mark_done("speaker_roles")
    ctx.write_json(
        "understanding/speakers.json",
        _minimal_speakers(_meta={"resilience": {"partial": True}}),
        skip_handoff=True,
    )
    with pytest.raises(SystemExit, match="Prerequisite artifact"):
        require_llm_stage_progress(ctx, "speaker_roles")


def test_require_llm_stage_progress_rejects_empty_partial(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _resilience_cfg())
    ctx = isolated_run_ctx(tmp_path, "res_upstream_bad")
    ctx.mark_done("speaker_roles")
    path = ctx.path("understanding", "speakers.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"speakers": [], "_meta": {"resilience": {"partial": True}}}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="Prerequisite artifact"):
        require_llm_stage_progress(ctx, "speaker_roles")


def test_llm_stage_progress_ok_strict_blocks_partial(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _resilience_cfg())
    ctx = isolated_run_ctx(tmp_path, "res_progress")
    ctx.write_json(
        "understanding/content_brief.json",
        _minimal_content_brief(_meta={"resilience": {"partial": True}}),
        skip_handoff=True,
    )
    envelope = {
        "status": "blocked",
        "needs": [],
        "_routing_meta": {"persist_action": "partial"},
    }
    assert not llm_stage_progress_ok(
        ctx,
        "content_context",
        envelope,
        schema_errors=["minor"],
        cfg=_resilience_cfg(),
    )
