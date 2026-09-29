"""Cached models load offline (ISSUES 84); skipped gap-fill outputs are not 'pending' (ISSUES 83)."""

from __future__ import annotations

import json
from pathlib import Path

from run_fixtures import isolated_run_ctx

from interview_mux import artifact_lifecycle as al
from interview_mux.musicgen_runner import hub_env_for_request


def _req(tmp_path: Path, **doc) -> Path:
    p = tmp_path / "cand_0.request.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _cache_with(tmp_path: Path, *model_ids: str) -> Path:
    cache = tmp_path / "hf_cache"
    for mid in model_ids:
        snap = cache / "hub" / ("models--" + mid.replace("/", "--")) / "snapshots" / "abc"
        snap.mkdir(parents=True, exist_ok=True)
    return cache


def test_cached_model_loads_offline_with_bounded_timeouts(tmp_path) -> None:
    cache = _cache_with(tmp_path, "facebook/musicgen-small")
    env = hub_env_for_request(_req(tmp_path, model_id="facebook/musicgen-small"), cache)
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["TRANSFORMERS_OFFLINE"] == "1"
    assert env["HF_HUB_ETAG_TIMEOUT"] == "10"


def test_uncached_model_may_fetch_but_never_hangs(tmp_path) -> None:
    cache = _cache_with(tmp_path)
    env = hub_env_for_request(_req(tmp_path, model_id="facebook/musicgen-small"), cache)
    assert "HF_HUB_OFFLINE" not in env
    assert env["HF_HUB_DOWNLOAD_TIMEOUT"] == "30"


def test_melody_model_must_be_cached_too(tmp_path) -> None:
    cache = _cache_with(tmp_path, "facebook/musicgen-small")
    env = hub_env_for_request(
        _req(tmp_path, model_id="facebook/musicgen-small", melody_model_id="facebook/musicgen-melody"),
        cache,
    )
    assert "HF_HUB_OFFLINE" not in env


def test_unreadable_request_still_bounds_timeouts(tmp_path) -> None:
    env = hub_env_for_request(tmp_path / "missing.json", tmp_path / "hf_cache")
    assert env["HF_HUB_ETAG_TIMEOUT"] == "10" and env["HF_HUB_DOWNLOAD_TIMEOUT"] == "30"
    assert "HF_HUB_OFFLINE" not in env


def test_skipped_gap_fill_outputs_read_as_skipped_not_pending(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_skipped_gap_fill")
    monkeypatch.setattr("interview_mux.gap_fill_eligibility.gap_fill_was_skipped", lambda c: True)
    rows = al.build_outputs_view(ctx, "gap_framing_compose")
    plan = next(r for r in rows if r["path"] == "understanding/gap_framing_plan.json")
    assert plan["phase"] == "skipped"
    assert plan["status"] == "skipped"
    assert al.stage_output_mode(ctx, "gap_framing_compose") == "optional_skipped"


def test_active_gap_fill_outputs_still_read_as_pending(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_active_gap_fill")
    monkeypatch.setattr("interview_mux.gap_fill_eligibility.gap_fill_was_skipped", lambda c: False)
    rows = al.build_outputs_view(ctx, "gap_framing_compose")
    plan = next(r for r in rows if r["path"] == "understanding/gap_framing_plan.json")
    assert plan["phase"] == "pending"
