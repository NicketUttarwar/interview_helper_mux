"""A refused optional write is skipped quietly: no error line, no failure signature (ISSUES 90)."""

from __future__ import annotations

import json

import pytest
from run_fixtures import isolated_run_ctx

from interview_mux import artifact_ownership as ao


def _deny(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ao, "write_permitted", lambda *_a, **_k: (False, "not_allow:owner=someone_else")
    )


def test_refused_optional_write_leaves_the_file_alone_and_logs_info(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_optional_write")
    target = ctx.final_path("understanding", "episode_structure.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"segment_order": ["seg_001"]}), encoding="utf-8")
    _deny(monkeypatch)
    denials: list[str] = []
    monkeypatch.setattr(ao, "_log_authority_denied", lambda _c, exc: denials.append(str(exc)))
    logged: list[tuple[str, str]] = []
    monkeypatch.setattr(ctx, "log", lambda msg, level="info", **_k: logged.append((level, msg)))

    out = ctx.write_json(
        "understanding/episode_structure.json", {"segment_order": ["seg_002"]}, optional=True
    )

    assert out == target
    assert json.loads(target.read_text(encoding="utf-8")) == {"segment_order": ["seg_001"]}
    assert denials == []
    assert logged and logged[0][0] == "info" and "optional write skipped" in logged[0][1]
    assert not ctx.final_path("operator", "forensics_errors.json").exists()


def test_refused_required_write_still_denies(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_required_write")
    _deny(monkeypatch)
    with pytest.raises(ao.AuthorityDenied):
        ctx.write_json("understanding/episode_structure.json", {"segment_order": []})


def test_permitted_optional_write_lands(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_optional_ok")
    monkeypatch.setattr(ao, "write_permitted", lambda *_a, **_k: (True, ""))
    ctx.write_json("analysis/optional_write_probe.json", {"version": 1, "ok": True}, optional=True)
    doc = json.loads(ctx.final_path("analysis", "optional_write_probe.json").read_text(encoding="utf-8"))
    assert doc == {"version": 1, "ok": True}
