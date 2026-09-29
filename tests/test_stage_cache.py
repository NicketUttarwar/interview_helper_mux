"""The stage cache restores heavy deterministic outputs on a rerun of the same source (ISSUES 93)."""

from __future__ import annotations

import json

import pytest
from run_fixtures import isolated_run_ctx

from interview_mux import stage_cache


@pytest.fixture
def cache_root(tmp_path, monkeypatch):
    root = tmp_path / "stage_cache"
    monkeypatch.setattr(stage_cache, "cache_root", lambda ctx=None: root)
    monkeypatch.delenv("MUX_STAGE_CACHE", raising=False)
    return root


def test_store_then_restore_writes_the_same_documents(tmp_path, cache_root) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_cache_store")
    key = stage_cache.cache_key("transcribe", "abc", "model", "sortformer", "cfg")
    docs = {
        "transcript/full.json": {"words": [{"w": "hi"}]},
        "transcript/speakers.json": {"speakers": [{"speaker_id": "spk_0"}]},
    }
    assert stage_cache.store(ctx, "transcribe", key, docs) is True

    other = isolated_run_ctx(tmp_path, "exec_cache_restore")
    written: dict[str, object] = {}
    other.write_json = lambda rel, doc, **_k: written.__setitem__(rel, doc)  # type: ignore[assignment]
    assert stage_cache.restore(other, "transcribe", key, list(docs)) is True
    assert written == docs


def test_a_different_key_is_a_miss(tmp_path, cache_root) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_cache_miss")
    key = stage_cache.cache_key("transcribe", "abc", "model", "sortformer", "cfg")
    stage_cache.store(ctx, "transcribe", key, {"transcript/full.json": {}})
    other_key = stage_cache.cache_key("transcribe", "abc", "other-model", "sortformer", "cfg")
    assert stage_cache.lookup(ctx, "transcribe", other_key, ["transcript/full.json"]) is None
    assert stage_cache.restore(ctx, "transcribe", other_key, ["transcript/full.json"]) is False


def test_partial_entries_are_a_miss(tmp_path, cache_root) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_cache_partial")
    key = stage_cache.cache_key("audio_probe_build", "t", "w", "c")
    stage_cache.store(ctx, "audio_probe_build", key, {"analysis/run_golden_facts.json": {"run": {}}})
    assert (
        stage_cache.lookup(
            ctx,
            "audio_probe_build",
            key,
            ["analysis/run_golden_facts.json", "transcript/protected_zones.json"],
        )
        is None
    )


def test_env_switch_disables_the_cache(tmp_path, cache_root, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_cache_off")
    key = stage_cache.cache_key("transcribe", "x")
    stage_cache.store(ctx, "transcribe", key, {"transcript/full.json": {"words": []}})
    monkeypatch.setenv("MUX_STAGE_CACHE", "0")
    assert stage_cache.lookup(ctx, "transcribe", key, ["transcript/full.json"]) is None
    assert stage_cache.store(ctx, "transcribe", key, {"transcript/full.json": {}}) is False


def test_file_digest_changes_with_bytes(tmp_path) -> None:
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    a.write_bytes(b"RIFF" + b"\0" * 32)
    b.write_bytes(b"RIFF" + b"\1" * 32)
    assert stage_cache.file_digest(a) != stage_cache.file_digest(b)
    assert stage_cache.file_digest(tmp_path / "missing.wav") == "missing"


def test_cache_root_sits_beside_the_executions(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MUX_STAGE_CACHE", raising=False)
    monkeypatch.setattr(stage_cache, "cache_cfg", lambda cfg=None: {"enabled": True, "root": ""})

    class _Ctx:
        executions_root = tmp_path / "executions"

    assert stage_cache.cache_root(_Ctx()) == tmp_path / "stage_cache"
    entry = json.loads(json.dumps({"ok": True}))
    assert entry == {"ok": True}
