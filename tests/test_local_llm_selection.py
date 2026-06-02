"""Tests for llmfit JSON parsing and model selection policy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.local_llm_selection import (
    MIN_QUALITY_SCORE,
    filter_candidates,
    parse_llmfit_candidates,
    pick_best_candidate,
    select_from_llmfit_json,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_llmfit_candidates_mlx_only() -> None:
    data = _load_fixture("llmfit_recommend.json")
    candidates = parse_llmfit_candidates(data)
    names = {c.model_id for c in candidates}
    assert "mlx-community/Qwen2.5-7B-Instruct-4bit" in names
    assert "meta-llama/Llama-3.1-8B-Instruct" not in names
    assert len(candidates) == 5


def test_filter_excludes_marginal_and_low_quality() -> None:
    data = _load_fixture("llmfit_recommend.json")
    candidates = parse_llmfit_candidates(data)
    eligible = filter_candidates(candidates, min_quality=MIN_QUALITY_SCORE)
    names = {c.model_id for c in eligible}
    assert "mlx-community/Some-Huge-Model-4bit" not in names
    assert "mlx-community/Tiny-Low-Quality-4bit" not in names
    assert "mlx-community/Qwen2.5-7B-Instruct-4bit" in names


def test_pick_best_prefers_max_context() -> None:
    data = _load_fixture("llmfit_recommend.json")
    candidates = parse_llmfit_candidates(data)
    best = pick_best_candidate(candidates)
    assert best is not None
    assert best.model_id == "mlx-community/Qwen2.5-7B-Instruct-4bit"
    assert best.context_length == 32768


def test_select_from_llmfit_json_returns_best() -> None:
    data = _load_fixture("llmfit_recommend.json")
    best, all_rows = select_from_llmfit_json(data)
    assert best is not None
    assert best.model_id == "mlx-community/Qwen2.5-7B-Instruct-4bit"
    assert len(all_rows) == 5


def test_select_returns_none_when_no_eligible() -> None:
    data = {
        "models": [
            {
                "name": "mlx-community/Bad-4bit",
                "fit": "marginal",
                "quality": 80,
                "context": 100000,
            }
        ]
    }
    best, _ = select_from_llmfit_json(data)
    assert best is None


def test_normalize_top_level_array() -> None:
    data = [
        {
            "name": "mlx-community/Foo-4bit",
            "fit": "good",
            "quality": 50,
            "context": 4096,
        }
    ]
    candidates = parse_llmfit_candidates(data)
    assert len(candidates) == 1
    assert candidates[0].model_id == "mlx-community/Foo-4bit"


def test_scores_nested_quality() -> None:
    data = {
        "models": [
            {
                "name": "mlx-community/Nested-4bit",
                "fit": "good",
                "scores": {"quality": 55, "context": 12000},
                "score": 60,
            }
        ]
    }
    candidates = parse_llmfit_candidates(data)
    assert candidates[0].quality == 55
    assert candidates[0].context_length == 12000
