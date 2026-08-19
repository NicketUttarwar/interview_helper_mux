"""Homunculus 0.0.0 / 0.1.0 rails — no live OpenAI."""

from __future__ import annotations

import json
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
    assert normalize_version(None) == "0.1.0"
    assert normalize_version("latest") == "0.1.0"
    with pytest.raises(ValueError, match="Unknown"):
        normalize_version("9.9.9")


def test_default_is_highest_registered() -> None:
    from interview_mux.homunculus.version import default_version, highest_version

    assert highest_version() == "0.1.0"
    assert default_version() == "0.1.0"


def test_000_is_not_homunculus_run() -> None:
    ctx = _ctx_000()
    assert is_homunculus_run(ctx) is False


def test_010_is_homunculus_run() -> None:
    ctx = _ctx_010()
    assert is_homunculus_run(ctx) is True


def test_fourth_invoke_refused() -> None:
    ctx = _ctx_010()

    def _ok() -> None:
        ctx.mark_done("mix", force=True)

    for _ in range(3):
        dispatch_stage(ctx, "mix", _ok, source="test")
    with pytest.raises(LimitExhausted):
        dispatch_stage(ctx, "mix", _ok, source="test")
    assert ctx.artifact_exists("mastering/homunculus/limit_exhausted.json")


def _write_boundaries(ctx: RunContext) -> None:
    path = ctx.path("segments/boundaries.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"boundaries": []}', encoding="utf-8")


def test_failed_stage_invokes_do_not_burn_cap() -> None:
    ctx = _ctx_010()

    def _boom() -> None:
        raise RuntimeError("pre-stage lifecycle failed")

    for _ in range(3):
        with pytest.raises(RuntimeError, match="pre-stage"):
            dispatch_stage(ctx, "boundary_detection", _boom, source="test")
    assert count_identity(ctx, "boundary_detection") == 0
    dispatch_stage(ctx, "boundary_detection", lambda: _write_boundaries(ctx), source="test")
    assert count_identity(ctx, "boundary_detection") == 1


def test_nested_llm_does_not_burn_stage_identity_cap() -> None:
    ctx = _ctx_010()

    def _boom() -> None:
        raise RuntimeError("pre-stage lifecycle failed")

    for _ in range(2):
        with pytest.raises(RuntimeError, match="pre-stage"):
            dispatch_stage(ctx, "boundary_detection", _boom, source="test")
    for i in range(3):
        append_ledger(
            ctx,
            {"kind": "llm", "identity": "boundary_detection", "status": "started"},
        )
        append_ledger(
            ctx,
            {"kind": "llm", "identity": "boundary_detection", "status": "done"},
        )
    assert count_identity(ctx, "boundary_detection") == 0
    dispatch_stage(ctx, "boundary_detection", lambda: _write_boundaries(ctx), source="test")
    assert count_identity(ctx, "boundary_detection") == 1


def test_hollow_stage_done_with_pending_writes_does_not_burn_cap() -> None:
    ctx = _ctx_010()
    pending = ctx.path(".pending_writes/mastering_research_waves/mastering/research")
    pending.mkdir(parents=True, exist_ok=True)
    (pending / "waves.json").write_text('{"version": 1}', encoding="utf-8")
    for _ in range(3):
        append_ledger(
            ctx,
            {"kind": "stage", "identity": "mastering_research_waves", "status": "started"},
        )
        append_ledger(
            ctx,
            {"kind": "stage", "identity": "mastering_research_waves", "status": "done"},
        )
    assert not ctx.is_done("mastering_research_waves")
    assert count_identity(ctx, "mastering_research_waves") == 0


def test_conductor_turn_uses_conductor_cap_not_stage_cap() -> None:
    """Stage identities cap at 3; conductor_turn must keep the run-wide turn budget."""
    ctx = _ctx_010()
    for _ in range(4):
        check_dispatch(ctx, identity="conductor_turn", kind="conductor_turn")
        append_ledger(ctx, {"kind": "conductor_turn", "identity": "conductor_turn"})
    assert count_identity(ctx, "conductor_turn") == 4
    assert not ctx.artifact_exists("mastering/homunculus/limit_exhausted.json")


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
    (ctx.run_dir / ".stage_done" / "transcript_review").write_text("", encoding="utf-8")
    ctx.write_json("ingest/transcript.json", {"text": "Hello I am Jordan with me today is Sam."})
    pack = pack_volley(ctx, fact_ids=[], tool_id="speaker_roles")
    blob = " ".join(t["content"] for t in pack["turns"])
    assert "Jordan" in blob
    assert pack["g0_bootstrapped"] is True
    assert "run_meta" not in blob
    assert "stage_done" not in blob


def test_bootstrap_g0_from_transcript_full_and_integrity_alias() -> None:
    ctx = _ctx_010()
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "transcript_review").write_text("", encoding="utf-8")
    ctx.write_json("transcript/full.json", {"text": "Late tape proof about circulating tumour cells."})
    pack = pack_volley(ctx, fact_ids=["transcript_integrity"], tool_id="boundary_detection")
    blob = " ".join(t["content"] for t in pack["turns"])
    assert "circulating tumour cells" in blob
    assert pack["g0_bootstrapped"] is True
    assert "(no admitted facts; G0 not closed)" not in blob


def test_g0_pack_includes_full_transcript_not_12k_slice() -> None:
    ctx = _ctx_010()
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "transcript_review").write_text("", encoding="utf-8")
    body = ("word " * 8000).strip()
    ctx.write_json("transcript/full.json", {"text": body + " UNIQUE_TAIL_TOKEN"})
    pack = pack_volley(ctx, fact_ids=[], tool_id="boundary_detection")
    blob = " ".join(t["content"] for t in pack["turns"])
    assert "UNIQUE_TAIL_TOKEN" in blob
    assert "part " in blob.lower() or len(blob) > 12000


def test_g0_pack_prefers_timestamped_words_over_untimed_text() -> None:
    ctx = _ctx_010()
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "transcript_review").write_text("", encoding="utf-8")
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "The Life Sciences without times",
            "words": [
                {"text": "The", "start_ms": 0, "end_ms": 560, "speaker_id": "spk_0"},
                {"text": "Life", "start_ms": 560, "end_ms": 780, "speaker_id": "spk_0"},
            ],
            "segments": [],
        },
    )
    pack = pack_volley(ctx, fact_ids=[], tool_id="boundary_detection")
    blob = " ".join(t["content"] for t in pack["turns"])
    assert "spk_0" in blob
    assert "0.00-" in blob
    assert "without times" not in blob


def test_coverage_pack_includes_brief_and_manifest() -> None:
    ctx = _ctx_010()
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "transcript_review").write_text("", encoding="utf-8")
    ctx.write_json("transcript/full.json", {"text": "hello tape"})
    from run_fixtures import minimal_content_brief

    ctx.write_json(
        "understanding/content_brief.json",
        minimal_content_brief(thesis="CTDNA thesis UNIQUE_BRIEF"),
        skip_handoff=True,
    )
    man_path = ctx.run_dir / "segments" / "manifest.json"
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "segment_id": "seg_001",
                        "start_ms": 0,
                        "end_ms": 1000,
                        "speaker_id": "spk_0",
                        "text": "hello tape",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    pack = pack_volley(ctx, fact_ids=["source_card"], tool_id="topic_coverage_audit")
    blob = " ".join(t["content"] for t in pack["turns"])
    assert "UNIQUE_BRIEF" in blob
    assert "seg_001" in blob


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


def test_completed_packet_hash_may_retry() -> None:
    ctx = _ctx_010()
    ph = packet_hash_for([{"role": "user", "content": "same"}])
    append_ledger(ctx, {"kind": "llm", "identity": "speaker_roles", "packet_hash": ph, "status": "started"})
    append_ledger(ctx, {"kind": "llm", "identity": "speaker_roles", "packet_hash": ph, "status": "done"})
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
    assert body["default"] == "0.1.0"
    ids = {b["id"] for b in body["brains"]}
    assert {"0.0.0", "0.1.0"} <= ids
    by_id = {b["id"]: b for b in body["brains"]}
    assert by_id["0.1.0"].get("is_default") is True
    assert by_id["0.0.0"].get("is_default") is False

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
    assert ok.json()["homunculus_version"] == "0.1.0"
    meta = (tmp_path / "ASSETS" / "executions" / ok.json()["run_id"] / "run_meta.json").read_text(
        encoding="utf-8"
    )
    assert '"homunculus_version": "0.1.0"' in meta


def test_write_json_admits_on_010() -> None:
    ctx = _ctx_010()
    ctx.write_json("scratch/probe.json", {"text": "tape"})
    from interview_mux.homunculus.admit import read_admitted

    facts = [r.get("fact_id") for r in read_admitted(ctx)]
    assert "write:scratch/probe.json" in facts


def test_write_json_does_not_admit_on_000() -> None:
    ctx = _ctx_000()
    ctx.write_json("scratch/probe.json", {"text": "tape"})
    from interview_mux.homunculus.admit import read_admitted

    assert read_admitted(ctx) == []


def test_persist_skip_on_replay() -> None:
    ctx = _ctx_010()
    admit(ctx, identity="x", action="keep", payload={"ok": True}, fact_id="fx")
    persist_artifact(ctx, "scratch/once.json", {"ok": True}, fact_id="fx")
    persist_artifact(ctx, "scratch/once.json", {"ok": True}, fact_id="fx")
    from interview_mux.homunculus.ledger import read_ledger

    dones = [
        r
        for r in read_ledger(ctx)
        if r.get("kind") == "persist" and r.get("status") == "done" and r.get("rel") == "scratch/once.json"
    ]
    assert len(dones) == 1


def test_recovery_blocked_until_analysis() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.runtime import recovery_allowed

    issue = emit_issue(ctx, kind="stage_failure", source="t", stage_id="edl", implicated=["edl"])
    assert recovery_allowed(ctx, "edl") is False
    analyze_issue(ctx, issue["issue_id"], quality_hypothesis="seam", action="retry")
    assert recovery_allowed(ctx, "edl") is True


def test_end_judgment_reads_listen_delight_audit_not_legacy_path() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.judge import after_complete_master

    ctx.write_json(
        "mastering/listen_delight_audit.json",
        {"failed_dimensions": ["recommendability"], "passed": False},
    )
    out = after_complete_master(ctx)
    assert out["verdict"] == "reject"
    assert "recommendability" in out["reason"]


def test_end_judgment_accept_requires_ears_or_fail_open() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.judge import write_judgment

    with pytest.raises(RuntimeError, match="ears"):
        write_judgment(ctx, verdict="accept", reason="no ears")
    out = write_judgment(
        ctx,
        verdict="accept",
        reason="fail open",
        fail_open_reason="speech venv unavailable",
    )
    assert out["verdict"] == "accept"


def test_ears_fail_open_missing_wav() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.ears import stt_window

    row = stt_window(ctx, window_id="opening", rel="master/master.wav", start_ms=0, end_ms=1000)
    assert row["fail_open"] is True
    assert row["qc_only"] is True
    assert row["overwrites_apple_vtt"] is False


def test_resolve_ears_wav_falls_back_to_assembly() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.ears import resolve_ears_wav_rel

    assembly = ctx.path("master/assembly.wav")
    assembly.parent.mkdir(parents=True, exist_ok=True)
    assembly.write_bytes(b"RIFF")
    assert resolve_ears_wav_rel(ctx) == "master/assembly.wav"
    master = ctx.path("master/master.wav")
    master.write_bytes(b"RIFF")
    assert resolve_ears_wav_rel(ctx) == "master/master.wav"


def test_end_judgment_defers_accept_without_wav() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.judge import after_complete_master

    out = after_complete_master(ctx)
    assert out["verdict"] == "pending"
    assert not ctx.artifact_exists("mastering/homunculus/end_judgment.json")


def test_gate_cannot_skip_g0() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.gates import set_gate_decision

    with pytest.raises(RuntimeError, match="cannot skip"):
        set_gate_decision(ctx, "transcript_integrity", "skip")
    doc = set_gate_decision(ctx, "framing_consent", "present_operator")
    assert doc["decisions"]["framing_consent"]["action"] == "present_operator"


def test_perspective_attaches_only_on_010() -> None:
    from interview_mux.stages.llm_runner import load_system_prompt_for_stage

    ctx = _ctx_010()
    text = load_system_prompt_for_stage(
        "selection/full-master-ranking.system.txt",
        "full_master_ranking",
        include_preamble=False,
        ctx=ctx,
    )
    assert "subscribe" in text.lower() or "listener" in text.lower()
    ctx0 = _ctx_000()
    text0 = load_system_prompt_for_stage(
        "selection/full-master-ranking.system.txt",
        "full_master_ranking",
        include_preamble=False,
        ctx=ctx0,
    )
    assert "Hard omit" not in text0


def test_seed_agenda_fallback_ledgered(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import run_homunculus_phase
    from interview_mux.homunculus.ledger import read_ledger

    ctx = _ctx_010()
    walked: list[tuple[list[str], str]] = []

    def _walk(_ctx, stages, *, reason: str) -> None:
        walked.append((list(stages), reason))

    monkeypatch.setattr("interview_mux.homunculus.agenda.walk_seed_agenda", _walk)

    class Boom:
        def create(self, **kwargs):
            raise RuntimeError("no network")

    client = SimpleNamespace(chat=SimpleNamespace(completions=Boom()))
    run_homunculus_phase(ctx, "analysis", ["speaker_roles"], client=client)
    kinds = [r.get("kind") for r in read_ledger(ctx)]
    identities = [r.get("identity") for r in read_ledger(ctx)]
    assert "fallback" in kinds
    assert "agenda" in kinds
    assert "conductor_error" in identities
    assert walked == []


def test_promote_prompt_requires_corpus() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.prompts import mint_prompt, promote_prompt

    mint_prompt(ctx, "m1", "Keep intros.", runtime="openai")
    denied = promote_prompt(ctx, "m1", corpus_ok=False)
    assert denied["ok"] is False
    ok = promote_prompt(ctx, "m1", corpus_ok=True)
    assert ok["ok"] is True


def test_run_analysis_uses_agenda_not_silent_linear(monkeypatch) -> None:
    ctx = _ctx_010()
    called: list[str] = []

    def _phase(_ctx, phase, remaining, **_kwargs):
        called.append(phase)
        return {"conductor": {"ok": True}, "remaining_after": []}

    monkeypatch.setattr("interview_mux.homunculus.agenda.run_homunculus_phase", _phase)
    from interview_mux.pipeline import run_analysis

    monkeypatch.setattr("interview_mux.pipeline.check_transcript_review_pending", lambda _c: False)
    monkeypatch.setattr(
        "interview_mux.analysis_memory.update_completion_from_analysis",
        lambda _c: {},
    )
    run_analysis(ctx)
    assert called == ["analysis"]


def test_no_automatic_leftover_walk() -> None:
    from interview_mux.homunculus.agenda import remaining_stages, run_homunculus_phase

    ctx = _ctx_010()

    class Msg:
        content = "stop"
        tool_calls = []

    class _C:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=Msg())])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_C()))
    out = run_homunculus_phase(ctx, "analysis", ["speaker_roles"], client=client)
    assert out["remaining_after"]
    assert "speaker_roles" in remaining_stages(ctx, "analysis")


def test_walk_seed_remainder_is_explicit(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import request_walk_seed_remainder, run_homunculus_phase

    ctx = _ctx_010()
    walked: list[str] = []

    def _walk(_ctx, stages, *, reason: str) -> None:
        walked.extend(stages)

    monkeypatch.setattr("interview_mux.homunculus.agenda.walk_seed_agenda", _walk)

    class Msg:
        content = "stop"
        tool_calls = []

    class _C:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=Msg())])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_C()))
    request_walk_seed_remainder(ctx, reason="test")
    run_homunculus_phase(ctx, "analysis", ["speaker_roles"], client=client)
    assert "speaker_roles" in walked
    assert walked[0] == "speaker_roles"
    assert "boundary_detection" not in walked


def test_walk_seed_does_not_rewind_before_planned(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import request_walk_seed_remainder, run_homunculus_phase

    ctx = _ctx_010()
    walked: list[str] = []

    def _walk(_ctx, stages, *, reason: str) -> None:
        walked.extend(stages)

    monkeypatch.setattr("interview_mux.homunculus.agenda.walk_seed_agenda", _walk)

    class Msg:
        content = "stop"
        tool_calls = []

    class _C:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=Msg())])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_C()))
    request_walk_seed_remainder(ctx, reason="test")
    run_homunculus_phase(ctx, "analysis", ["missing_framing"], client=client)
    assert walked == ["missing_framing"]


def test_remaining_stages_uses_seed_order_not_scheduled_reorder() -> None:
    from interview_mux.homunculus.agenda import remaining_stages, write_agenda

    ctx = _ctx_010()
    write_agenda(ctx, "analysis", ["boundary_detection"], source="test")
    ctx.write_json(
        "mastering/homunculus/agenda.json",
        {
            "phase": "analysis",
            "remaining": ["content_brief_reanchor"],
            "source": "conductor",
            "seed_order": [],
            "skipped": [],
            "scheduled": [
                "boundary_topic_resplit",
                "segment_classification",
                "boundary_detection",
                "content_brief_reanchor",
            ],
            "reruns": [],
        },
    )
    rem = remaining_stages(ctx, "analysis")
    assert rem.index("boundary_detection") < rem.index("boundary_topic_resplit")
    assert rem.index("boundary_detection") < rem.index("content_brief_reanchor")
    assert "content_brief_reanchor" in rem


def test_skip_without_done_marker_stays_in_remaining() -> None:
    from interview_mux.homunculus.agenda import remaining_stages, write_agenda

    ctx = _ctx_010()
    write_agenda(ctx, "analysis", ["content_brief_reanchor"], source="test")
    ctx.write_json(
        "mastering/homunculus/agenda.json",
        {
            "phase": "analysis",
            "remaining": ["boundary_topic_resplit"],
            "source": "conductor",
            "seed_order": [],
            "skipped": ["content_brief_reanchor"],
            "scheduled": [],
            "reruns": [],
        },
    )
    rem = remaining_stages(ctx, "analysis")
    assert "content_brief_reanchor" in rem
    assert rem.index("content_brief_reanchor") < rem.index("boundary_topic_resplit")


def test_skip_island_stage_without_artifacts_refused() -> None:
    from interview_mux.homunculus.agenda import skip_stage

    ctx = _ctx_010()
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, "low_conf_island_scan", reason="nah")
    ctx.write_json("analysis/low_conf_must_keep.json", {"segment_ids": ["seg_1"]})
    doc = skip_stage(ctx, "low_conf_island_scan", reason="already have islands")
    assert "low_conf_island_scan" in doc["skipped"]
    assert ctx.is_done("low_conf_island_scan")


def test_skip_core_analysis_stage_without_artifact_refused() -> None:
    from interview_mux.homunculus.agenda import skip_stage

    ctx = _ctx_010()
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, "ideal_cuts_propose", reason="coverage miss")
    ctx.path("understanding/ideal_cuts.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("understanding/ideal_cuts.json").write_text('{"cuts": [{"cut_id": "c1"}]}', encoding="utf-8")
    doc = skip_stage(ctx, "ideal_cuts_propose", reason="already proposed")
    assert "ideal_cuts_propose" in doc["skipped"]
    assert ctx.is_done("ideal_cuts_propose")


def test_persist_analysis_complete_before_episode_structure_refused() -> None:
    ctx = _ctx_010()
    admit(
        ctx,
        identity="write:analysis_complete.json",
        action="keep",
        payload={"ok": True},
        fact_id="write:analysis_complete.json",
    )
    with pytest.raises(RuntimeError, match="episode_structure_compose"):
        persist_artifact(
            ctx,
            "analysis_complete.json",
            {"ok": True},
            fact_id="write:analysis_complete.json",
        )


def test_surgical_rerun_does_not_clear_from(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import rerun_stage, unmark_stage_only

    ctx = _ctx_010()
    done = ctx.final_path(".stage_done", "speaker_roles")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("", encoding="utf-8")
    later = ctx.final_path(".stage_done", "content_context")
    later.write_text("", encoding="utf-8")
    seq = unmark_stage_only(ctx, "speaker_roles")
    assert seq >= 1
    assert not ctx.is_done("speaker_roles")
    assert ctx.is_done("content_context")

    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage",
        lambda _c, stage: ran.append(stage),
    )
    rerun_stage(ctx, "speaker_roles")
    assert ran == ["speaker_roles"]
    assert ctx.is_done("content_context")


def _close_g0(ctx: RunContext, text: str = "Hello from the reviewed tape.") -> None:
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "transcript_review").write_text("", encoding="utf-8")
    ctx.write_json("transcript/full.json", {"text": text})


def test_g0_closed_false_on_fresh_run() -> None:
    from interview_mux.homunculus.packer import g0_closed

    ctx = _ctx_010()
    assert g0_closed(ctx) is False
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "transcribe").write_text("", encoding="utf-8")
    assert g0_closed(ctx) is False


def test_rerun_transcribe_refused_when_g0_closed(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import rerun_stage

    ctx = _ctx_010()
    _close_g0(ctx)
    done = ctx.final_path(".stage_done", "transcribe")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("", encoding="utf-8")
    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage",
        lambda _c, stage: ran.append(stage),
    )
    with pytest.raises(RuntimeError, match="G0 is closed"):
        rerun_stage(ctx, "transcribe")
    assert ran == []
    assert ctx.is_done("transcribe")


def test_rerun_segment_classification_refused_when_manifest_classified(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import rerun_stage

    ctx = _ctx_010()
    _close_g0(ctx)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 800,
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest_story"],
                    "text": "classified already",
                }
            ]
        },
    )
    done = ctx.final_path(".stage_done", "segment_classification")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("", encoding="utf-8")
    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage",
        lambda _c, stage: ran.append(stage),
    )
    with pytest.raises(RuntimeError, match="pack segment_manifest"):
        rerun_stage(ctx, "segment_classification")
    assert ran == []
    assert ctx.is_done("segment_classification")


def test_dispatch_run_stage_transcribe_refused_when_g0_closed(monkeypatch) -> None:
    ctx = _ctx_010()
    _close_g0(ctx)
    done = ctx.final_path(".stage_done", "transcribe")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("", encoding="utf-8")
    ran: list[str] = []
    with pytest.raises(RuntimeError, match="G0 is closed"):
        dispatch_stage(ctx, "transcribe", lambda: ran.append("ran"), source="conductor")
    assert ran == []
    assert ctx.is_done("transcribe")


def test_dispatch_runs_transcribe_on_fresh_run() -> None:
    ctx = _ctx_010()
    ran: list[str] = []

    def _impl() -> None:
        ran.append("ran")
        ctx.write_json("transcript/full.json", {"text": "fresh tape"})

    dispatch_stage(ctx, "transcribe", _impl, source="conductor")
    assert ran == ["ran"]


def test_hollow_transcribe_done_is_unmarked_and_run() -> None:
    from interview_mux.homunculus.agenda import unmark_hollow_prepare_stages

    ctx = _ctx_010()
    done = ctx.final_path(".stage_done", "transcribe")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("", encoding="utf-8")
    ingest = ctx.final_path(".stage_done", "ingest")
    ingest.write_text("", encoding="utf-8")
    cleared = unmark_hollow_prepare_stages(ctx)
    assert "transcribe" in cleared
    assert "ingest" in cleared
    assert not ctx.is_done("transcribe")
    assert not ctx.is_done("ingest")
    ran: list[str] = []

    def _impl() -> None:
        ran.append("ran")
        ctx.write_json("transcript/full.json", {"text": "repaired tape"})

    dispatch_stage(ctx, "transcribe", _impl, source="conductor")
    assert ran == ["ran"]


def test_nested_chat_create_packs_user_turn() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.source_card import build_source_card

    build_source_card(ctx)
    captured: list[dict] = []

    class _C:
        def create(self, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(id="r")

    client = SimpleNamespace(chat=SimpleNamespace(completions=_C()))
    nested_chat_create(
        ctx,
        "speaker_roles",
        client,
        {"model": "x", "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "dump"}]},
    )
    blob = str(captured[0]["messages"])
    assert "dump" not in blob
    assert any(m.get("role") == "system" for m in captured[0]["messages"])
    assert "source_card" in blob or "source_card" in str(captured)


def test_apply_pack_keeps_host_layup_stage_packet() -> None:
    from interview_mux.homunculus.packer import apply_pack_to_kwargs

    ctx = _ctx_010()
    host = json.dumps(
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "natives": [
                {
                    "segment_id": "seg_001",
                    "text": "hello from the native beat " + ("x" * 80),
                    "already_aired_nugget_ids": [],
                    "opening_owner": False,
                }
            ],
            "nugget_corpus": {"nuggets": []},
        }
    )
    out = apply_pack_to_kwargs(
        ctx,
        "nugget_layup_compose",
        {"messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": host}]},
    )
    user = " ".join(str(m.get("content")) for m in out["messages"] if m.get("role") == "user")
    assert "already_aired_nugget_ids" in user
    assert "seg_001" in user
    assert "--- stage input ---" in user


def test_missing_framing_packs_manifest_not_empty_transcript_segments() -> None:
    """G0 words without transcript.segments must not starve gap eval of segment_id."""
    from interview_mux.homunculus.packer import apply_pack_to_kwargs, default_pack_fact_ids

    ctx = _ctx_010()
    _close_g0(ctx)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "timestamped tape",
            "segments": [],
            "words": [
                {"word": "hello", "start": 0.0, "end": 0.4, "speaker": "spk_0"},
                {"word": "there", "start": 0.4, "end": 0.8, "speaker": "spk_0"},
            ],
        },
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 800,
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest_story"],
                    "text": "hello there from the classified manifest",
                }
            ]
        },
    )
    ids = default_pack_fact_ids(ctx, "missing_framing")
    assert "segment_manifest" in ids
    assert "g0_transcript" not in ids
    host = json.dumps(
        {
            "content_brief": {"thesis": "guest story"},
            "segments": [
                {
                    "segment_id": "seg_001",
                    "speaker_role": "interviewee",
                    "text": "hello there from the classified manifest " + ("x" * 80),
                }
            ],
        }
    )
    out = apply_pack_to_kwargs(
        ctx,
        "missing_framing",
        {"messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": host}]},
    )
    user = " ".join(str(m.get("content")) for m in out["messages"] if m.get("role") == "user")
    assert "seg_001" in user
    assert "interviewee" in user
    assert "--- stage input ---" in user
    assert "G0 transcript (closed)" not in user
    assert "[g0_transcript" not in user


def test_omit_g0_drops_g0_even_when_fact_ids_ask_for_it() -> None:
    from interview_mux.homunculus.packer import pack_volley

    ctx = _ctx_010()
    _close_g0(ctx, "UNIQUE_G0_MARKER_WORDS")
    pack = pack_volley(
        ctx,
        fact_ids=["g0_transcript"],
        tool_id="missing_framing",
        omit_g0=True,
    )
    blob = str(pack.get("turns") or "")
    assert "UNIQUE_G0_MARKER_WORDS" not in blob
    assert "G0 transcript (closed)" not in blob


def test_nested_chat_packs_during_open_stage() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.source_card import build_source_card

    build_source_card(ctx)
    append_ledger(ctx, {"kind": "stage", "identity": "boundary_detection", "status": "started"})
    captured: list[dict] = []

    class _C:
        def create(self, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(id="r")

    client = SimpleNamespace(chat=SimpleNamespace(completions=_C()))
    nested_chat_create(
        ctx,
        "boundary_detection",
        client,
        {"model": "x", "messages": [{"role": "user", "content": "dump"}]},
    )
    blob = str(captured[0]["messages"])
    assert "dump" not in blob
    # Open stage rows do not burn the identity cap until .stage_done exists.
    assert count_identity(ctx, "boundary_detection") == 0


def test_dispatch_stage_without_required_artifact_is_failure() -> None:
    ctx = _ctx_010()
    with pytest.raises(RuntimeError, match="without required artifact"):
        dispatch_stage(ctx, "boundary_detection", lambda: None, source="test")
    assert count_identity(ctx, "boundary_detection") == 0
    assert not ctx.artifact_exists("segments/boundaries.json")


def test_speaker_scoped_second_analysis_allowed() -> None:
    ctx = _ctx_010()
    a = emit_issue(
        ctx, kind="stage_failure", source="t", stage_id="edl", implicated=["edl"], speaker_id="spk_a"
    )
    b = emit_issue(
        ctx, kind="stage_failure", source="t", stage_id="edl", implicated=["edl"], speaker_id="spk_b"
    )
    assert a["issue_id"] != b["issue_id"]
    analyze_issue(ctx, a["issue_id"], quality_hypothesis="a", action="retry", style="rushed")
    analyze_issue(ctx, b["issue_id"], quality_hypothesis="b", action="retry", style="calm")
    from interview_mux.homunculus.kb import read_kb

    styles = read_kb(ctx).get("styles") or []
    assert len(styles) >= 2


def test_same_speaker_duplicate_analysis_refused() -> None:
    ctx = _ctx_010()
    issue = emit_issue(
        ctx, kind="stage_failure", source="t", stage_id="mix", implicated=["mix"], speaker_id="spk_a"
    )
    analyze_issue(ctx, issue["issue_id"], quality_hypothesis="mud", action="retry")
    with pytest.raises(RuntimeError, match="already ran"):
        analyze_issue(ctx, issue["issue_id"], quality_hypothesis="again", action="retry")


def test_ear_windows_are_source_relative() -> None:
    from interview_mux.homunculus.ears import plan_ear_windows

    ctx = _ctx_010()
    short = plan_ear_windows(ctx, 9000)
    assert len(short) == 1
    assert short[0][2] <= 9000
    longw = plan_ear_windows(ctx, 3_600_000)
    assert len(longw) == 3
    assert longw[0][2] < 3_600_000
    assert longw[-1][1] >= int(3_600_000 * 0.9)
    assert all(end <= 3_600_000 for _n, _s, end in longw)


def test_reject_writes_kb_lessons() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.judge import write_judgment
    from interview_mux.homunculus.kb import lesson_ids
    from interview_mux.homunculus.packer import default_pack_fact_ids

    ctx.write_json(
        "mastering/listen_delight_audit.json",
        {"failed_dimensions": ["conversation_fit"], "passed": False},
    )
    write_judgment(
        ctx,
        verdict="reject",
        reason="conversation_fit",
        implicated_groups=["mix"],
        fail_open_reason="n/a",
    )
    ids = lesson_ids(ctx)
    assert ids
    packed = default_pack_fact_ids(ctx, "mix")
    assert any(i in packed for i in ids)


def test_host_musicgen_not_queued(monkeypatch) -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.host_tools import run_musicgen_host

    def _fake_gen(**kwargs):
        return {
            "backend": "musicgen",
            "fidelity_step": "ladder_large",
            "model_id": "facebook/musicgen-large",
        }

    monkeypatch.setattr("interview_mux.musicgen_runner.generate_music_clip", _fake_gen)
    out = run_musicgen_host(ctx, {"prompt": "motif", "role": "theme_underscore"})
    assert out.get("queued") is not True
    assert out["ok"] is True
    assert out.get("fidelity_step") == "ladder_large"
    from interview_mux.homunculus.kb import musicgen_large_aborted, read_kb

    assert musicgen_large_aborted(ctx) is False
    assert read_kb(ctx).get("musicgen", {}).get("last_backend") == "musicgen"


def test_mmaudio_first_refused_for_creative_beds() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.host_tools import run_mmaudio_host

    denied = run_mmaudio_host(ctx, {"prompt": "bed", "role": "theme_underscore"})
    assert denied["ok"] is False
    assert denied["error"] == "prefer_musicgen_first"


def test_conductor_cap_uses_remaining_turns() -> None:
    from interview_mux.homunculus.budget import remaining_conductor_turns
    from interview_mux.homunculus.loop import run_conductor

    ctx = _ctx_010()
    assert remaining_conductor_turns(ctx) >= 12

    class Msg:
        content = "done"
        tool_calls = []

    class _C:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=Msg())])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_C()))
    out = run_conductor(ctx, user_message="hi", client=client)
    assert out["ok"] is True
    assert out["turns"] == 1

