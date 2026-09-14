"""HS-3: pre-ranking writer identity + analysis skip audit stub.

pass_id=pre_ranking stamps shared bounds/manifest as
connector_fuse_pass_pre_ranking. Analysis skip/disabled/empty-packet writes
analysis/connector_fuse_audit.json. Wrapper enabled=false does not return empty.

Do not start a run. HS-1 remainder/refresh cap, HS-4 oscillation pin, HS-2 resplit stay.
Keep test_pre_ranking_fuse_not_satisfied_by_first_pass_audit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from interview_mux.homunculus.agenda import stage_outputs_present
from interview_mux.run_context import RunContext
from interview_mux.segment_fuse import (
    FUSE_AUDIT_PATH,
    FUSE_ROUNDS_PATH,
    fuse_writer_stage,
    run_connector_fuse_pass,
)
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    stage_artifact_incompleteness,
)
from interview_mux.stages.low_conf_fuse_stages import (
    run_connector_fuse_pass as wrapper_fuse_pass,
)
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hs3_fuse")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _disabled_cfg(_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"enabled": False, "max_fuses_per_pass": 24, "max_fuse_rounds": 8}


def test_hs3_fuse_writer_stage_maps_pre_ranking() -> None:
    assert fuse_writer_stage("pre_ranking") == "connector_fuse_pass_pre_ranking"
    assert fuse_writer_stage("pre_ranking:high_value") == "connector_fuse_pass_pre_ranking"
    assert fuse_writer_stage("post_sanitize") == "connector_fuse_pass"
    assert fuse_writer_stage("junction_heal") == "connector_fuse_pass"
    assert fuse_writer_stage("") == "connector_fuse_pass"


def test_hs3_disabled_writes_audit_stub_and_heal_marks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("interview_mux.segment_fuse.connector_fuse_cfg", _disabled_cfg)
    result = run_connector_fuse_pass(ctx, pass_id="post_sanitize")
    assert result.get("skip_reason") == "disabled"
    assert ctx.artifact_exists(FUSE_AUDIT_PATH)
    assert ctx.artifact_exists(FUSE_ROUNDS_PATH)
    rounds = ctx.read_json(FUSE_ROUNDS_PATH)
    assert rounds.get("pass_id") == "post_sanitize"
    audit = ctx.read_json(FUSE_AUDIT_PATH)
    assert any(
        isinstance(p, dict) and p.get("skip_reason") == "disabled" for p in (audit.get("passes") or [])
    )
    assert stage_artifact_incompleteness(ctx, "connector_fuse_pass") is None
    heal_or_refuse_mark(ctx, "connector_fuse_pass", force=True)
    assert ctx.is_done("connector_fuse_pass")
    assert stage_outputs_present(ctx, "connector_fuse_pass") is True
    assert stage_outputs_present(ctx, "connector_fuse_pass_pre_ranking") is False


def test_hs3_missing_manifest_writes_audit_stub(ctx: RunContext) -> None:
    assert not ctx.artifact_exists("segments/manifest.json")
    result = run_connector_fuse_pass(ctx, pass_id="post_sanitize")
    assert result.get("skip_reason") == "missing_manifest"
    assert ctx.artifact_exists(FUSE_AUDIT_PATH)
    assert ctx.artifact_exists(FUSE_ROUNDS_PATH)


def test_hs3_wrapper_disabled_writes_stub_not_empty(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("interview_mux.segment_fuse.connector_fuse_cfg", _disabled_cfg)
    monkeypatch.setattr(
        "interview_mux.stages.low_conf_fuse_stages.connector_fuse_cfg", _disabled_cfg
    )
    wrapper_fuse_pass(ctx)
    assert ctx.artifact_exists(FUSE_AUDIT_PATH)
    assert ctx.artifact_exists(FUSE_ROUNDS_PATH)
    rounds = ctx.read_json(FUSE_ROUNDS_PATH)
    assert rounds.get("pass_id") == "post_sanitize"
    assert rounds.get("skip_reason") == "disabled"


def test_hs3_empty_packets_writes_audit(ctx: RunContext) -> None:
    path = ctx.final_path("segments", "manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"segments": []}', encoding="utf-8")
    result = run_connector_fuse_pass(ctx, pass_id="post_sanitize")
    assert int(result.get("total_applied") or 0) == 0
    assert ctx.artifact_exists(FUSE_AUDIT_PATH)
    audit = ctx.read_json(FUSE_AUDIT_PATH)
    assert any(
        isinstance(p, dict) and p.get("skip_reason") == "empty_packets"
        for p in (audit.get("passes") or [])
    )


def test_hs3_pre_ranking_skip_writes_rounds_not_analysis_audit(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("interview_mux.segment_fuse.connector_fuse_cfg", _disabled_cfg)
    result = run_connector_fuse_pass(ctx, pass_id="pre_ranking")
    assert result.get("skip_reason") == "disabled"
    rounds = ctx.read_json(FUSE_ROUNDS_PATH)
    assert rounds.get("pass_id") == "pre_ranking"
    assert stage_outputs_present(ctx, "connector_fuse_pass_pre_ranking") is True
    assert not ctx.artifact_exists(FUSE_AUDIT_PATH)
    assert stage_outputs_present(ctx, "connector_fuse_pass") is False


def test_hs3_pre_ranking_fuse_stamps_pre_ranking_publisher() -> None:
    from interview_mux.segment_fuse import _write_boundaries, _write_manifest

    keys: list[tuple[str, str | None]] = []

    class _Fake:
        def __init__(self) -> None:
            self._store: dict[str, Any] = {}

        def artifact_exists(self, rel: str) -> bool:
            return rel in self._store

        def read_json(self, rel: str) -> Any:
            return self._store[rel]

        def write_json(self, rel: str, doc: Any, **kwargs: Any) -> Path:
            self._store[rel] = doc
            keys.append((rel, kwargs.get("stage_key")))
            return Path(".")

        def log(self, *args: Any, **kwargs: Any) -> None:
            return None

    segs = [
        {
            "segment_id": "a",
            "start_ms": 0,
            "end_ms": 1000,
            "text": "we started building because",
            "speaker_id": "spk_0",
        },
        {
            "segment_id": "b",
            "start_ms": 1100,
            "end_ms": 2200,
            "text": "the buyers were snacking",
            "speaker_id": "spk_0",
        },
    ]
    fake = _Fake()
    fake._store["segments/manifest.json"] = {"segments": segs}
    fake._store["segments/boundaries.json"] = {"boundaries": [dict(s) for s in segs]}
    _write_manifest(fake, segs[:1], pass_id="pre_ranking")  # type: ignore[arg-type]
    _write_boundaries(fake, segs[:1], consumed={"b"}, pass_id="pre_ranking")  # type: ignore[arg-type]
    assert ("segments/manifest.json", "connector_fuse_pass_pre_ranking") in keys
    assert ("segments/boundaries.json", "connector_fuse_pass_pre_ranking") in keys
    bounds = fake._store["segments/boundaries.json"]
    publisher = ((bounds.get("_meta") or {}).get("segment_contract") or {}).get("publisher_stage")
    if publisher is not None:
        assert publisher == "connector_fuse_pass_pre_ranking"


def test_hs3_analysis_fuse_still_stamps_connector_fuse_pass() -> None:
    from interview_mux.segment_fuse import _write_boundaries, _write_manifest

    keys: list[tuple[str, str | None]] = []

    class _Fake:
        def __init__(self) -> None:
            self._store: dict[str, Any] = {}

        def artifact_exists(self, rel: str) -> bool:
            return rel in self._store

        def read_json(self, rel: str) -> Any:
            return self._store[rel]

        def write_json(self, rel: str, doc: Any, **kwargs: Any) -> Path:
            self._store[rel] = doc
            keys.append((rel, kwargs.get("stage_key")))
            return Path(".")

        def log(self, *args: Any, **kwargs: Any) -> None:
            return None

    segs = [
        {
            "segment_id": "a",
            "start_ms": 0,
            "end_ms": 1000,
            "text": "we started building because",
            "speaker_id": "spk_0",
        }
    ]
    fake = _Fake()
    fake._store["segments/manifest.json"] = {"segments": segs}
    fake._store["segments/boundaries.json"] = {"boundaries": [dict(s) for s in segs]}
    _write_manifest(fake, segs, pass_id="post_sanitize")  # type: ignore[arg-type]
    _write_boundaries(fake, segs, consumed=set(), pass_id="post_sanitize")  # type: ignore[arg-type]
    assert ("segments/manifest.json", "connector_fuse_pass") in keys
    assert ("segments/boundaries.json", "connector_fuse_pass") in keys


def test_hs3_raw_done_without_audit_is_incomplete(ctx: RunContext) -> None:
    mark_done_raw(ctx, "connector_fuse_pass")
    reason = stage_artifact_incompleteness(ctx, "connector_fuse_pass")
    assert reason
    assert "connector_fuse_audit" in str(reason)
    heal_or_refuse_mark(ctx, "connector_fuse_pass", force=True)
    assert not ctx.is_done("connector_fuse_pass")
