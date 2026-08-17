"""Homunculus 0.0.0 / 0.1.0 rails — no live OpenAI."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from interview_mux.homunculus.admit import admit, persist_artifact
from interview_mux.homunculus.budget import LimitExhausted, check_audio_serialize, check_dispatch
from interview_mux.homunculus.coverage import assert_coverage_complete, coverage_report
from interview_mux.homunculus.issues import analyze_issue, emit_issue
from interview_mux.homunculus.ledger import append_ledger, count_identity, packet_hash_for
from interview_mux.homunculus.loop import nested_chat_create, run_conductor
from interview_mux.homunculus.packer import pack_volley
from interview_mux.homunculus.runtime import dispatch_stage, is_homunculus_run
from interview_mux.homunculus.values import should_hard_omit_cta
from interview_mux.homunculus.version import normalize_version
from interview_mux.run_context import RunContext
from interview_mux.volley_packet_lint import strip_forbidden_metadata


def _ctx_010() -> RunContext:
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
    )
    return ctx


def _ctx_000() -> RunContext:
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.0.0", "homunculus_kind": "original_pipeline"},
    )
    return ctx


def test_normalize_version_default_and_unknown() -> None:
    assert normalize_version("0.0.0") == "0.0.0"
    assert normalize_version("0.1.0") == "0.1.0"
    with pytest.raises(ValueError, match="Unknown"):
        normalize_version("9.9.9")


def test_000_is_not_homunculus_run() -> None:
    ctx = _ctx_000()
    assert is_homunculus_run(ctx) is False


def test_010_is_homunculus_run() -> None:
    ctx = _ctx_010()
    assert is_homunculus_run(ctx) is True


def test_fourth_invoke_refused() -> None:
    ctx = _ctx_010()
    for _ in range(3):
        dispatch_stage(ctx, "mix", lambda: None, source="test")
    with pytest.raises(LimitExhausted):
        dispatch_stage(ctx, "mix", lambda: None, source="test")
    assert ctx.artifact_exists("mastering/homunculus/limit_exhausted.json")


def test_second_issue_analysis_refused() -> None:
    ctx = _ctx_010()
    issue = emit_issue(ctx, kind="stage_failure", source="t", stage_id="edl", implicated=["edl"])
    analyze_issue(ctx, issue["issue_id"], quality_hypothesis="seam", action="retry")
    with pytest.raises(RuntimeError, match="already ran"):
        analyze_issue(ctx, issue["issue_id"], quality_hypothesis="again", action="retry")


def test_admit_drop_refuses_persist() -> None:
    ctx = _ctx_010()
    rec = admit(ctx, identity="ranking", action="drop", payload={"ids": [1]}, fact_id="f_drop")
    assert rec["action"] == "drop"
    with pytest.raises(RuntimeError, match="persist refused"):
        persist_artifact(ctx, "master/selection.json", {"ids": [1]}, fact_id="f_drop")


def test_bootstrap_g0_pack_with_empty_store() -> None:
    ctx = _ctx_010()
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "transcript_review_build").write_text("", encoding="utf-8")
    ctx.write_json("ingest/transcript.json", {"text": "Hello I am Jordan with me today is Sam."})
    pack = pack_volley(ctx, fact_ids=[], tool_id="speaker_roles")
    blob = " ".join(t["content"] for t in pack["turns"])
    assert "Jordan" in blob
    assert pack["g0_bootstrapped"] is True
    assert "run_meta" not in blob
    assert "stage_done" not in blob


def test_pack_never_includes_run_meta() -> None:
    ctx = _ctx_010()
    admit(
        ctx,
        identity="junk",
        action="keep",
        payload={"run_meta": {"secret": 1}, "text": "tape meaning", "exists": True},
        fact_id="f1",
    )
    pack = pack_volley(ctx, fact_ids=["f1"], tool_id="ranking")
    blob = str(pack)
    assert "secret" not in blob
    stripped = strip_forbidden_metadata({"run_meta": 1, "ok": True})
    assert "run_meta" not in stripped


def test_starvation_when_required_fact_missing() -> None:
    ctx = _ctx_010()
    with pytest.raises(RuntimeError, match="starvation_ranking"):
        pack_volley(ctx, fact_ids=[], tool_id="edl", require_facts=["ranking"])


def test_cta_omit_and_keep_intro() -> None:
    assert should_hard_omit_cta("Please like and subscribe and buy now") is True
    assert should_hard_omit_cta("Our two-sided market lets other businesses pay") is False
    from interview_mux.homunculus.speakers import build_speaker_dossier

    ctx = _ctx_010()
    ctx.write_json("ingest/transcript.json", {"text": "Hi I'm Jordan and with me today is Sam."})
    dossier = build_speaker_dossier(ctx)
    names = {row["name"] for row in dossier["intro_spans"]}
    assert "Jordan" in names or "Sam" in names
    assert dossier["invented_names"] is False


def test_audio_serialize_refuses_parallel() -> None:
    ctx = _ctx_010()
    with pytest.raises(LimitExhausted) as exc:
        check_audio_serialize(ctx, "mix", {"transcribe"})
    assert exc.value.reason == "audio_serialize"


def test_crash_replay_ledger_before_effect() -> None:
    ctx = _ctx_010()
    append_ledger(ctx, {"kind": "persist", "identity": "persist_artifact", "status": "started", "rel": "x.json"})
    admit(ctx, identity="x", action="keep", payload={"ok": True}, fact_id="fx")
    persist_artifact(ctx, "mastering/homunculus/memory_probe.json", {"ok": True}, fact_id="fx")
    assert count_identity(ctx, "persist_artifact") >= 1


def test_nested_chat_create_passthrough_on_000() -> None:
    ctx = _ctx_000()
    calls: list[dict] = []

    class _C:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_C()))
    nested_chat_create(ctx, "speaker_roles", client, {"model": "x", "messages": []})
    assert len(calls) == 1
    assert not ctx.artifact_exists("mastering/homunculus/ledger.json")


def test_schema_retry_does_not_double_count() -> None:
    ctx = _ctx_010()
    append_ledger(
        ctx,
        {"kind": "llm", "identity": "speaker_roles", "status": "started", "packet_hash": "x"},
    )

    class _C:
        def create(self, **kwargs):
            return SimpleNamespace(id="r")

    client = SimpleNamespace(chat=SimpleNamespace(completions=_C()))
    nested_chat_create(ctx, "speaker_roles", client, {"model": "x", "messages": []})
    assert count_identity(ctx, "speaker_roles") == 1


def test_identical_packed_call_once() -> None:
    ctx = _ctx_010()
    ph = packet_hash_for([{"role": "user", "content": "same"}])
    check_dispatch(ctx, identity="speaker_roles", kind="llm")
    append_ledger(ctx, {"kind": "llm", "identity": "speaker_roles", "packet_hash": ph, "status": "started"})
    with pytest.raises(LimitExhausted):
        check_dispatch(ctx, identity="speaker_roles", kind="llm", packet_hash=ph)


def test_coverage_complete() -> None:
    report = coverage_report()
    assert report["ok"], report
    assert_coverage_complete()


def test_conductor_stub_no_network() -> None:
    ctx = _ctx_010()

    class Fn:
        def __init__(self) -> None:
            self.name = "admit_result"
            self.arguments = '{"identity": "t", "action": "keep"}'

    class Tc:
        id = "call_1"
        function = Fn()

    class Msg:
        content = ""
        tool_calls = [Tc()]

    class Msg2:
        content = "done"
        tool_calls = []

    creates = [
        SimpleNamespace(choices=[SimpleNamespace(message=Msg())]),
        SimpleNamespace(choices=[SimpleNamespace(message=Msg2())]),
    ]

    class _C:
        def create(self, **kwargs):
            assert kwargs.get("parallel_tool_calls") is False
            return creates.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=_C()))
    out = run_conductor(ctx, user_message="admit the last result", client=client, max_turns=4)
    assert out["ok"] is True
    assert out["turns"] >= 1


def test_versions_api_and_create_run_stamps(tmp_path, monkeypatch) -> None:
    import shutil
    from interview_mux.config import repo_root as real_repo_root
    from interview_mux.web.server import create_app

    shutil.copytree(real_repo_root() / "config", tmp_path / "config")
    monkeypatch.setenv("INTERVIEW_MUX_ROOT", str(tmp_path))
    assets = tmp_path / "ASSETS"
    (assets / "input").mkdir(parents=True)
    (assets / "executions").mkdir(parents=True)
    (assets / "input" / "interview.wav").write_bytes(
        b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )
    client = TestClient(create_app())
    vers = client.get("/api/homunculus/versions")
    assert vers.status_code == 200
    body = vers.json()
    assert body["default"] == "0.0.0"
    ids = {b["id"] for b in body["brains"]}
    assert {"0.0.0", "0.1.0"} <= ids

    bad = client.post(
        "/api/runs",
        json={
            "input_audio_path": "ASSETS/input/interview.wav",
            "homunculus_version": "9.9.9",
        },
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/runs",
        json={"input_audio_path": "ASSETS/input/interview.wav", "run_mode": "manual"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["homunculus_version"] == "0.0.0"
    meta = (tmp_path / "ASSETS" / "executions" / ok.json()["run_id"] / "run_meta.json").read_text(
        encoding="utf-8"
    )
    assert '"homunculus_version": "0.0.0"' in meta
