"""Hard-fix plan: must-keep, e2e_soft, spoken-copy, packet lint, runtime JSON."""

from __future__ import annotations

from typing import Any

from interview_mux.e2e_soft import e2e_soft_enabled
from interview_mux.hard_keep import enforce_hard_keeps, hard_keep_segment_ids
from interview_mux.local_runtime import classify_runtime_error, parse_runtime_json_stdout
from interview_mux.spoken_copy_guard import spoken_copy_violations
from interview_mux.volley_packet_lint import lint_llm_user_payload, strip_forbidden_metadata


class _FakeCtx:
    def __init__(self, store: dict[str, Any] | None = None):
        self._store = store or {}

    def artifact_exists(self, rel: str) -> bool:
        return rel in self._store

    def read_json(self, rel: str) -> Any:
        return self._store[rel]

    def log(self, *args: Any, **kwargs: Any) -> None:
        return None


def test_e2e_soft_default_off(monkeypatch):
    monkeypatch.delenv("INTERVIEW_MUX_E2E_SOFT", raising=False)
    assert e2e_soft_enabled(meta={"e2e_soft_listen_delight": True}) is False
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    assert e2e_soft_enabled(meta={"e2e_soft_listen_delight": True}) is True


def test_hard_keep_restores_vanish_from_both():
    ctx = _FakeCtx(
        {
            "understanding/ideal_cuts.json": {"must_keep_segment_ids": ["seg_keep"]},
            "understanding/talking_points.json": {
                "talking_points": [{"must_keep": True, "segment_id": "seg_tp"}]
            },
        }
    )
    keeps = hard_keep_segment_ids(ctx)
    assert "seg_keep" in keeps
    assert "seg_tp" in keeps
    out = enforce_hard_keeps(
        ctx,
        {
            "ordered_segment_ids": ["seg_other"],
            "excluded_segment_ids": [{"segment_id": "seg_keep", "reason": "aside"}],
        },
    )
    assert "seg_keep" in out["ordered_segment_ids"]
    assert "seg_tp" in out["ordered_segment_ids"]
    excl_ids = {
        (e.get("segment_id") if isinstance(e, dict) else e)
        for e in out["excluded_segment_ids"]
    }
    assert "seg_keep" not in excl_ids


def test_spoken_copy_imperatives_not_entities():
    ev = {
        "strict_grounding": True,
        "target_excerpt": "Bham told a war story that stuck",
        "before_excerpt": "we kept going",
    }
    for line in (
        "Listen for the one that stuck",
        "Brace for his war-story",
        "Remember, Bham",
    ):
        errs = spoken_copy_violations(line, evidence=ev)
        assert not any(e.startswith("spoken_unsupported_entity") for e in errs), (line, errs)


def test_volley_lint_strips_metadata():
    cleaned = strip_forbidden_metadata(
        {
            "transcript": "hello from tape",
            "stage_done": True,
            "path_ok": True,
            "run_meta": {"e2e_soft": True},
            "nested": {"exists": True, "segment_text": "keep me"},
        }
    )
    assert "stage_done" not in cleaned
    assert "path_ok" not in cleaned
    assert "run_meta" not in cleaned
    assert cleaned["transcript"] == "hello from tape"
    assert "exists" not in cleaned["nested"]
    out = lint_llm_user_payload({"transcript": "x" * 50, "e2e_heal": True})
    assert "e2e_heal" not in out


def test_runtime_json_prefers_last_object_and_classifies():
    raw = "loading weights...\n{\"ok\": false, \"error\": \"missing voice ref\"}\n"
    parsed = parse_runtime_json_stdout(raw)
    assert parsed and parsed.get("ok") is False
    assert classify_runtime_error("missing voice reference wav", "") == "missing_voice_ref"
    assert classify_runtime_error("CUDA OOM", "") == "oom"


def test_pick_best_order_reports_dropped():
    from interview_mux.rank_candidates import pick_best_order

    pick = pick_best_order(
        [
            {"source": "a", "ordered_segment_ids": ["s1", "s2"]},
            {"source": "b", "ordered_segment_ids": ["s1", "s2", "s3"]},
        ]
    )
    assert "dropped_segment_ids" in pick
    assert set(pick["dropped_segment_ids"]) <= {"s1", "s2", "s3"}


def test_spoken_copy_entity_rewrite_before_omit():
    from interview_mux.spoken_copy_guard import guard_spoken_copy

    ev = {
        "strict_grounding": True,
        "target_excerpt": "we kept the tape rolling",
        "before_excerpt": "the room went quiet",
    }
    decision = guard_spoken_copy(
        "Mallory kept the tape rolling",
        evidence=ev,
        required=False,
        purpose="test",
    )
    assert decision["action"] in {"fallback", "allow"}
    assert decision["text"]
    assert "Mallory" not in decision["text"]


def test_lint_require_tape_rejects_empty():
    import pytest

    with pytest.raises(ValueError, match="tape-derived"):
        lint_llm_user_payload({"exists": True, "stage_done": True}, require_tape=True)


def test_connector_fuse_defaults_unbounded():
    from interview_mux.segment_fuse import _DEFAULTS

    assert int(_DEFAULTS["max_fuses_per_pass"] or 0) == 0
    assert int(_DEFAULTS["max_fuse_rounds"] or 0) == 0
