from __future__ import annotations

import json

import pytest

from interview_mux.llm_simple import StageError
from interview_mux.mastering_llm import (
    artifacts_from_envelope,
    classify_mastering_artifact_failure,
    invoke_mastering_prompt,
    mastering_failure_predicate_token,
)
from interview_mux.mastering_shape_runtime import _shape_llm_user_payload
from interview_mux.run_context import RunContext
from interview_mux.thrash_hardening import (
    FAIL_CLASS_MASTERING_SHAPE_HOLLOW,
    premature_fail_class,
)
from run_fixtures import patch_executions_root


@pytest.fixture
def ctx(tmp_path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("exec_category_b_ws1", create=True)


def test_nested_shape_artifacts_are_unwrapped() -> None:
    agenda = {"version": 1, "steps": []}
    assert artifacts_from_envelope({"mastering_shape_agenda": agenda}) == {
        "mastering_shape_agenda": agenda
    }
    rubric = {"version": 1, "criteria": []}
    assert artifacts_from_envelope({"mastering_eval_rubric": rubric}) == {
        "mastering_eval_rubric": rubric
    }


def test_typed_contract_failure_classes_and_fingerprint() -> None:
    wrong, wrong_errors = classify_mastering_artifact_failure(
        {"mastering_shape_agenda": {"version": 1}},
        required_artifact="mastering_shape_candidates",
        schema_file="mastering_shape_candidates.schema.json",
    )
    assert wrong == "wrong_artifact_envelope"
    empty, _ = classify_mastering_artifact_failure(
        {"mastering_shape_candidates": {"version": 1, "candidates": []}},
        required_artifact="mastering_shape_candidates",
        schema_file="mastering_shape_candidates.schema.json",
    )
    assert empty == "empty_primary"
    invalid, invalid_errors = classify_mastering_artifact_failure(
        {"mastering_eval_rubric": {"version": 1, "criteria": [{}]}},
        required_artifact="mastering_eval_rubric",
        schema_file="mastering_eval_rubric.schema.json",
    )
    assert invalid == "schema_invalid"
    token = mastering_failure_predicate_token(
        "mastering_shape_agenda", invalid, invalid_errors
    )
    assert token == mastering_failure_predicate_token(
        "mastering_shape_agenda", invalid, list(reversed(invalid_errors))
    )
    assert len(token) == 20
    assert wrong_errors


def test_one_typed_remutate_then_hard_halt(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []

    def fake_run(_stage, _prompt, *, user_content, **kwargs):
        calls.append({"payload": json.loads(user_content), **kwargs})
        return {
            "status": "complete",
            "artifacts": {
                "mastering_shape_agenda": {
                    "version": 1,
                    "steps": [],
                }
            },
        }

    monkeypatch.setattr(
        "interview_mux.stages.llm_runner.run_prompt_envelope", fake_run
    )
    with pytest.raises(StageError, match="wrong_artifact_envelope") as exc:
        invoke_mastering_prompt(
            ctx,
            "mastering_shape_candidates",
            "mastering/shape-l2-candidates.system.txt",
            {
                "artifact": "candidates",
                "evidence": {"items": [{"ref": "tape", "inline": {"text": "x"}}]},
            },
            max_attempts=2,
        )
    assert len(calls) == 2
    assert "remutate" not in calls[0]["payload"]
    assert calls[1]["payload"]["remutate"]["failure_class"] == (
        "wrong_artifact_envelope"
    )
    assert "predicate_token=" in str(exc.value)


def test_plan_paths_bind_plan_payload_and_shape_fail_class(ctx: RunContext) -> None:
    for pass_name in ("provisional", "confirmed"):
        payload = _shape_llm_user_payload(
            ctx,
            consumer_id=f"shape_{pass_name}",
            pass_name=pass_name,
            artifact="plan",
        )
        assert payload["artifact"] == "plan"
        assert payload["response_contract"]["required_artifact"] == "mastering_plan"
    assert (
        premature_fail_class("mastering_shape_candidates")
        == FAIL_CLASS_MASTERING_SHAPE_HOLLOW
    )
