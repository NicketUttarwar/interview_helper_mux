"""Homunculus 0.0.0 / 0.1.0 rails — no live OpenAI."""

from __future__ import annotations

import json
from pathlib import Path
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
from run_fixtures import (
    isolated_run_ctx,
    mark_done_raw,
    plant_seed_complete_through,
    write_fixture_json,
    write_fixture_theme_wav,
)


def _ctx_010() -> RunContext:
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
    )
    return ctx


def _mark_analysis_prefix(ctx: RunContext, upto_stage: str) -> None:
    """TH1b: fixture-stamp ANALYSIS_ORDER before ``upto_stage`` with prepare outputs."""
    from interview_mux.v2.config import ANALYSIS_ORDER

    idx = ANALYSIS_ORDER.index(upto_stage)
    prefix = ANALYSIS_ORDER[:idx]
    if "ingest" in prefix or "transcribe" in prefix or "audio_preclean" in prefix:
        wav = ctx.path("ingest", "normalized.wav")
        wav.parent.mkdir(parents=True, exist_ok=True)
        if not wav.is_file():
            wav.write_bytes(b"RIFF" + b"\x00" * 64)
    if "audio_preclean" in prefix:
        # unmark_hollow_prepare_stages requires any preclean output present.
        prov = ctx.path("preclean", "provider.json")
        prov.parent.mkdir(parents=True, exist_ok=True)
        if not prov.is_file():
            prov.write_text('{"status":"skipped","provider":"fixture"}', encoding="utf-8")
    if "transcribe" in prefix and not ctx.artifact_exists("transcript/full.json"):
        ctx.write_json(
            "transcript/full.json",
            {"text": "fixture tape", "segments": []},
            skip_handoff=True,
        )
    # Hollow-unmark at dispatch clears G0 prepare markers without a schema-valid queue.
    if "transcript_review_build" in prefix and not ctx.artifact_exists(
        "transcript/review_queue.json"
    ):
        ctx.write_json(
            "transcript/review_queue.json",
            {"chunks": []},
            skip_handoff=True,
        )
    mark_done_raw(ctx, *prefix)


def _plant_theme_wavs(ctx: RunContext) -> None:
    write_fixture_theme_wav(ctx, "master/assembly.wav")
    write_fixture_theme_wav(ctx, "master/assembly_preview.wav")
    if not ctx.artifact_exists("master/edl.json"):
        write_fixture_json(ctx, "master/edl.json", {"clips": []})
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        sdp = ctx.read_json("understanding/sound_design_plan.json")
        for asset in (sdp or {}).get("assets") or []:
            if isinstance(asset, dict) and asset.get("asset_id"):
                write_fixture_theme_wav(
                    ctx, f"sound_design/assets/{asset['asset_id']}.wav"
                )


def _open_preview_music(ctx: RunContext) -> None:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    epoch = dict(meta.get("delivery_epoch") or {})
    epoch["mix_junction_seat"] = {
        **dict(epoch.get("mix_junction_seat") or {}),
        "preview_music": True,
    }
    meta["delivery_epoch"] = epoch
    write_fixture_json(ctx, "run_meta.json", meta)


def _commit_assembly(ctx: RunContext) -> None:
    asm = ctx.final_path("master", "assembly.wav")
    if not asm.is_file():
        write_fixture_theme_wav(ctx, "master/assembly.wav")
        asm = ctx.final_path("master", "assembly.wav")
    write_fixture_json(
        ctx,
        "master/seam_autopsy.json",
        {
            "version": 1,
            "commitment": {
                "status": "committed",
                "assembly": {"exists": True, "size": asm.stat().st_size},
                "reasons": [],
            },
        },
    )


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
    assert normalize_version("0.2.0") == "0.2.0"
    assert normalize_version(None) == "0.2.0"
    assert normalize_version("latest") == "0.2.0"
    with pytest.raises(ValueError, match="Unknown"):
        normalize_version("9.9.9")


def test_default_is_highest_registered() -> None:
    from interview_mux.homunculus.version import default_version, highest_version

    assert highest_version() == "0.2.0"
    assert default_version() == "0.2.0"


def test_000_is_not_homunculus_run() -> None:
    ctx = _ctx_000()
    assert is_homunculus_run(ctx) is False


def test_010_is_homunculus_run() -> None:
    ctx = _ctx_010()
    assert is_homunculus_run(ctx) is True


def test_fourth_invoke_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx_010()
    import os
    import time

    # Unit test is about invoke identity caps, not mix seating completeness.
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime._seed_prereq_block",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.collect_stage_input_issues",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.upstream_stale_blockers",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.mix_epoch_block",
        lambda *_a, **_k: None,
    )

    def _ok() -> None:
        dest = ctx.path("master/assembly.wav")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"RIFF")
        edl = ctx.path("master/edl.json")
        edl.parent.mkdir(parents=True, exist_ok=True)
        edl.write_text(
            json.dumps(
                {
                    "version": 1,
                    "ordered_segment_ids": [],
                    "timeline_duration_ms": 0,
                    "clips": [],
                }
            ),
            encoding="utf-8",
        )
        now = time.time()
        os.utime(edl, (now - 10, now - 10))
        os.utime(dest, (now, now))
        # Direct marker — RIFF stub fails artifact_status even under _mark_done_raw.
        marker = ctx.final_path(".stage_done", "mix")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()

    for _ in range(3):
        dispatch_stage(ctx, "mix", _ok, source="test")
    with pytest.raises(LimitExhausted):
        dispatch_stage(ctx, "mix", _ok, source="test")
    assert ctx.artifact_exists("mastering/homunculus/limit_exhausted.json")


def _write_boundaries(ctx: RunContext) -> None:
    path = ctx.path("segments/boundaries.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "boundaries": [
                    {
                        "segment_id": "seg_001",
                        "start_ms": 0,
                        "end_ms": 4000,
                        "proposed_split_reason": "test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_failed_stage_invokes_do_not_burn_cap() -> None:
    ctx = _ctx_010()
    _mark_analysis_prefix(ctx, "boundary_detection")

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
    _mark_analysis_prefix(ctx, "boundary_detection")

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
    assert should_hard_omit_cta(
        "The Life Sciences DNA podcast is sponsored by Agilisium Labs."
    ) is True
    assert should_hard_omit_cta("This episode is presented by Acme Analytics.") is True
    assert should_hard_omit_cta("Brought to you by Contoso Labs — visit contoso.com") is True
    assert should_hard_omit_cta("Powered by NovaBio for this series.") is True
    assert should_hard_omit_cta("In partnership with Horizon Genomics.") is True
    assert should_hard_omit_cta(
        "Sponsored-by: BrandX (with punctuation noise)"
    ) is True
    assert should_hard_omit_cta(
        "Well, before we begin, I want to remind our audience that they can stay up on the latest episodes of Life Sciences DNA by hitting the subscribe button."
    ) is True
    assert should_hard_omit_cta(
        "To learn how Agilisium Labs can use generative AI, visit them at labs.agilisium.com"
    ) is True
    assert should_hard_omit_cta("hospitals subscribe to the protein snack model") is False
    assert should_hard_omit_cta(".agilisium .com.") is True
    assert should_hard_omit_cta(
        "Life Sciences DNA is a bi-monthly podcast produced by the Levine Media Group "
        "with production support from FullView Media."
    ) is True
    assert should_hard_omit_cta(
        "Music for this podcast is provided courtesy of the Jonah Levine Collective."
    ) is True
    assert should_hard_omit_cta(
        "Mohan, thanks for joining us. We're going to talk today about how AI is transforming cancer care."
    ) is False
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


def test_legacy_done_without_packet_hash_closes_sticky_identical_call() -> None:
    """exec_11165: specialist done rows omitted packet_hash → sticky identical_packed_call."""
    ctx = _ctx_010()
    ph = packet_hash_for([{"role": "user", "content": "legacy"}])
    append_ledger(
        ctx,
        {"kind": "llm", "identity": "full_master_ranking__stt_lexicon_island_verify", "packet_hash": ph, "status": "started"},
    )
    append_ledger(
        ctx,
        {"kind": "llm", "identity": "full_master_ranking__stt_lexicon_island_verify", "status": "done"},
    )
    check_dispatch(
        ctx,
        identity="full_master_ranking__stt_lexicon_island_verify",
        kind="llm",
        packet_hash=ph,
    )


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


@pytest.mark.real_executions_root  # test supplies its own INTERVIEW_MUX_ROOT
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
    assert body["default"] == "0.2.0"
    ids = {b["id"] for b in body["brains"]}
    assert {"0.0.0", "0.2.0"} <= ids
    assert "0.1.0" not in ids
    by_id = {b["id"]: b for b in body["brains"]}
    assert by_id["0.2.0"].get("is_default") is True
    assert by_id["0.2.0"].get("control_plane") == "deterministic"
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
    assert ok.json()["homunculus_version"] == "0.2.0"
    assert ok.json()["podcast_id"] == "zero_shot_podcast_demo"
    meta = (tmp_path / "ASSETS" / "executions" / ok.json()["run_id"] / "run_meta.json").read_text(
        encoding="utf-8"
    )
    assert '"homunculus_version": "0.2.0"' in meta
    assert '"podcast_id": "zero_shot_podcast_demo"' in meta


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
    # Unclassified novel failure still waits for analysis.
    assert recovery_allowed(ctx, "sonic_context_build") is False
    analyze_issue(ctx, issue["issue_id"], quality_hypothesis="seam", action="retry")
    assert recovery_allowed(ctx, "edl") is True
    assert recovery_allowed(ctx, "speaker_roles") is True
    assert recovery_allowed(ctx, "nugget_layup_compose") is True
    # Classified drift does not need analyze_issue.
    assert (
        recovery_allowed(
            ctx,
            "mix",
            exc=SystemExit("selection_edl_order_drift: speech clip order diverges"),
        )
        is True
    )


def test_dispatch_speaker_roles_mixed_diarization_persists(tmp_path) -> None:
    import json

    from interview_mux.homunculus.runtime import dispatch_stage
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "hom_mixed_diar")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    _mark_analysis_prefix(ctx, "speaker_roles")
    words = []
    t = 0
    for _ in range(40):
        words.append({"speaker": "spk_0", "word": "story", "start_ms": t, "end_ms": t + 400})
        t += 450
    for _ in range(8):
        words.append({"speaker": "spk_1", "word": "why?", "start_ms": t, "end_ms": t + 200})
        t += 250
    (ctx.run_dir / "transcript").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "transcript" / "full.json").write_text(
        json.dumps({"text": "dialogue", "words": words}),
        encoding="utf-8",
    )
    (ctx.run_dir / "transcript" / "speakers.json").write_text(
        json.dumps({"speakers": [{"speaker_id": "spk_0"}, {"speaker_id": "spk_1"}]}),
        encoding="utf-8",
    )

    def _boom() -> None:
        raise RuntimeError(
            "LLM stage speaker_roles incomplete: status=partial "
            "needs=[{'type': 'rerun_stage', 'stage': 'diarization', 'blocking': True}]"
        )

    dispatch_stage(ctx, "speaker_roles", _boom, source="test")
    assert ctx.is_done("speaker_roles")
    assert ctx.artifact_exists("understanding/speakers.json")


def test_end_judgment_reads_listen_delight_audit_not_legacy_path() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.judge import after_complete_master

    ctx.write_json(
        "mastering/listen_delight_audit.json",
        {"failed_dimensions": ["recommendability"], "passed": False},
    )
    wav = ctx.path("master", "master.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    out = after_complete_master(ctx)
    assert out["verdict"] in {"reject", "pending", "accept"}
    assert "recommendability" in out["reason"] or "delight" in out["reason"]


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


def test_resolve_ears_ignores_pending_master(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "ears_pending_master")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
    )
    from interview_mux.homunculus.ears import resolve_ears_wav_rel

    assembly = ctx.path("master/assembly.wav")
    assembly.parent.mkdir(parents=True, exist_ok=True)
    assembly.write_bytes(b"RIFF")
    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "master_finalize"
        / "master"
        / "master.wav"
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF")
    assert resolve_ears_wav_rel(ctx) == "master/assembly.wav"


def test_end_judgment_defers_accept_without_wav() -> None:
    ctx = _ctx_010()
    from interview_mux.homunculus.judge import after_complete_master

    out = after_complete_master(ctx)
    assert out["verdict"] == "pending"
    assert not ctx.artifact_exists("mastering/homunculus/end_judgment.json")


def test_end_judgment_ignores_pending_master(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "judge_pending_master")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
    )
    from interview_mux.homunculus.judge import after_complete_master

    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "master_finalize"
        / "master"
        / "master.wav"
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF" + b"\x00" * 64)
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


def test_publish_gate_ignores_pending_master(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "gate_pending_master")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
    )
    from interview_mux.gates import check_g_publish_pending
    from interview_mux.homunculus.gates import category_status

    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "master_finalize"
        / "master"
        / "master.wav"
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF" + b"\x00" * 64)
    assert check_g_publish_pending(ctx) is False
    assert category_status(ctx)["publish_package"]["open"] is False


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


def test_walk_seed_remainder_is_consumed_after_fallback() -> None:
    from interview_mux.homunculus.agenda import request_walk_seed_remainder
    from interview_mux.homunculus.ledger import append_ledger, remainder_requested

    ctx = _ctx_010()
    request_walk_seed_remainder(ctx, reason="test")
    assert remainder_requested(ctx) is True
    append_ledger(
        ctx,
        {
            "kind": "fallback",
            "identity": "walk_seed_agenda",
            "reason": "walk_seed_remainder",
        },
    )
    assert remainder_requested(ctx) is False


def _stop_client():
    class Msg:
        content = "stop"
        tool_calls = []

    class _C:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=Msg())])

    return SimpleNamespace(chat=SimpleNamespace(completions=_C()))


def _passing_pmq(ctx) -> None:
    pmq = ctx.path("master/post_master_quality.json")
    pmq.parent.mkdir(parents=True, exist_ok=True)
    pmq.write_text(
        '{"version": 1, "status": "pass", "publish_allowed": true, "failed_checks": []}',
        encoding="utf-8",
    )


def test_delivery_walks_ship_remainder_when_master_exists(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import run_homunculus_phase

    ctx = _ctx_010()
    master = ctx.path("master/master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 40)
    _passing_pmq(ctx)
    walked: list[tuple[str, tuple[str, ...]]] = []

    def _walk(_ctx, stages, *, reason: str) -> None:
        walked.append((reason, tuple(stages)))
        for sid in stages:
            mark_done_raw(_ctx, sid)

    monkeypatch.setattr("interview_mux.homunculus.agenda.walk_seed_agenda", _walk)
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.pending_analysis_for_delivery",
        lambda _c: [],
    )
    out = run_homunculus_phase(
        ctx,
        "delivery",
        ["episode_meta_build", "podcast_publish"],
        client=_stop_client(),
    )
    assert walked
    assert walked[0][0] == "delivery_walk_to_publish"
    assert walked[0][1][0] == "master_transcript_build"
    assert "episode_meta_build" in walked[0][1]
    assert "podcast_publish" in walked[0][1]
    assert "mix" not in walked[0][1]
    assert "master_transcript_build" not in (out.get("remaining_after") or [])


def test_delivery_walks_to_master_when_wav_missing(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import run_homunculus_phase

    ctx = _ctx_010()
    plant_seed_complete_through(ctx, "edl")
    _plant_theme_wavs(ctx)
    walked: list[str] = []

    def _walk(_ctx, stages, *, reason: str) -> None:
        walked.append(reason)

    monkeypatch.setattr("interview_mux.homunculus.agenda.walk_seed_agenda", _walk)
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.pending_analysis_for_delivery",
        lambda _c: [],
    )
    # No master.wav — conductor walks remaining seed toward mix/finalize.
    run_homunculus_phase(
        ctx,
        "delivery",
        ["mix", "master_finalize"],
        client=_stop_client(),
    )
    assert walked
    assert any("delivery" in reason or "walk" in reason for reason in walked)


def test_delivery_does_not_walk_ship_when_pmq_missing(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import run_homunculus_phase

    ctx = _ctx_010()
    master = ctx.path("master/master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 40)
    walked: list[tuple[str, tuple[str, ...]]] = []

    def _walk(_ctx, stages, *, reason: str) -> None:
        walked.append((reason, tuple(stages)))

    monkeypatch.setattr("interview_mux.homunculus.agenda.walk_seed_agenda", _walk)
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.pending_analysis_for_delivery",
        lambda _c: [],
    )
    run_homunculus_phase(
        ctx,
        "delivery",
        ["master_finalize", "podcast_publish"],
        client=_stop_client(),
    )
    assert walked
    assert walked[0][0] == "delivery_walk_unpublishable_master"
    assert "podcast_publish" not in walked[0][1]


def test_delivery_does_not_walk_ship_when_post_master_quality_failed(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import run_homunculus_phase

    ctx = _ctx_010()
    master = ctx.path("master/master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 40)
    pmq = ctx.path("master/post_master_quality.json")
    pmq.write_text(
        '{"version": 1, "status": "fail", "publish_allowed": false}',
        encoding="utf-8",
    )
    walked: list[tuple[str, tuple[str, ...]]] = []

    def _walk(_ctx, stages, *, reason: str) -> None:
        walked.append((reason, tuple(stages)))

    monkeypatch.setattr("interview_mux.homunculus.agenda.walk_seed_agenda", _walk)
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.pending_analysis_for_delivery",
        lambda _c: [],
    )
    run_homunculus_phase(
        ctx,
        "delivery",
        ["mix", "master_finalize", "podcast_publish"],
        client=_stop_client(),
    )
    assert walked
    assert walked[0][0] == "delivery_walk_unpublishable_master"
    assert "mix" in walked[0][1]
    assert "podcast_publish" not in walked[0][1]


def test_delivery_does_not_walk_pre_master_when_master_exists(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import run_homunculus_phase

    ctx = _ctx_010()
    master = ctx.path("master/master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 40)
    for rel in (
        "master/transcript.json",
        "publish/episode_meta.json",
        "publish/cover_prompt.json",
        "publish/chapters.json",
        "publish/package_ready.json",
    ):
        dest = ctx.path(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith("package_ready.json"):
            dest.write_text('{"ready": true}', encoding="utf-8")
        else:
            dest.write_text("{}", encoding="utf-8")
    cover = ctx.path("publish/cover.jpg")
    cover.parent.mkdir(parents=True, exist_ok=True)
    cover.write_bytes(b"\xff\xd8\xff")
    mp3 = ctx.path("publish/audio.mp3")
    mp3.parent.mkdir(parents=True, exist_ok=True)
    mp3.write_bytes(b"ID3")
    for sid in (
        "master_transcript_build",
        "episode_meta_build",
        "episode_cover_prompt_craft",
        "podcast_encode_mp3",
        "episode_cover_generate",
        "podcast_publish",
    ):
        mark_done_raw(ctx, sid)
    _passing_pmq(ctx)
    walked: list[str] = []

    def _walk(_ctx, stages, *, reason: str) -> None:
        walked.append(reason)

    monkeypatch.setattr("interview_mux.homunculus.agenda.walk_seed_agenda", _walk)
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.pending_analysis_for_delivery",
        lambda _c: [],
    )
    run_homunculus_phase(ctx, "delivery", ["mix"], client=_stop_client())
    assert walked == []


def test_backfill_delivery_holes_after_master_closes_vo_synthesize() -> None:
    from interview_mux.homunculus.agenda import backfill_delivery_holes_after_master

    ctx = _ctx_010()
    plant_seed_complete_through(ctx, "edl")
    _plant_theme_wavs(ctx)
    write_fixture_theme_wav(ctx, "master/master.wav")
    mark_done_raw(ctx, "master_finalize")
    mark_done_raw(ctx, "edl")
    done = ctx.final_path(".stage_done", "vo_synthesize")
    if done.is_file():
        done.unlink()
    filled = backfill_delivery_holes_after_master(ctx)
    assert "vo_synthesize" in filled
    assert ctx.is_done("vo_synthesize")
    assert ctx.artifact_exists("mastering/vo_synthesize.json")


def test_delivery_refuses_boundary_rewind_when_classified(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import write_agenda
    from interview_mux.homunculus.runtime import dispatch_stage

    ctx = _ctx_010()
    _close_g0(ctx)
    write_agenda(ctx, "delivery", ["topic_coverage_audit"], source="test")
    bpath = ctx.path("segments/boundaries.json")
    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(
        '{"boundaries":[{"segment_id":"seg_001","start_ms":0,"end_ms":8000,'
        '"proposed_split_reason":"pause"}]}',
        encoding="utf-8",
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 8000,
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest"],
                }
            ]
        },
    )
    done = ctx.final_path(".stage_done", "boundary_detection")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("", encoding="utf-8")
    ran: list[str] = []
    with pytest.raises(RuntimeError, match="timeline artifacts exist"):
        dispatch_stage(ctx, "boundary_detection", lambda: ran.append("ran"), source="conductor")
    assert ran == []


def test_g0_refuses_boundary_rewind_even_during_analysis() -> None:
    from interview_mux.homunculus.agenda import write_agenda
    from interview_mux.homunculus.runtime import dispatch_stage

    ctx = _ctx_010()
    _close_g0(ctx)
    write_agenda(ctx, "analysis", ["boundary_detection"], source="test")
    bpath = ctx.path("segments/boundaries.json")
    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(
        '{"boundaries":[{"segment_id":"seg_001","start_ms":0,"end_ms":8000,'
        '"proposed_split_reason":"pause"}]}',
        encoding="utf-8",
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 8000,
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest"],
                }
            ]
        },
    )
    ran: list[str] = []
    with pytest.raises(RuntimeError, match="timeline artifacts exist"):
        dispatch_stage(ctx, "boundary_detection", lambda: ran.append("ran"), source="conductor")
    assert ran == []


def test_pending_analysis_for_delivery_lists_missing_gap_artifacts() -> None:
    from interview_mux.homunculus.agenda import pending_analysis_for_delivery

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "speaker_role": "interviewee",
                    "speaker_id": "spk_1",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest"],
                    "start_ms": 0,
                    "end_ms": 8000,
                }
            ]
        },
    )
    bpath = ctx.path("segments/boundaries.json")
    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(
        '{"boundaries":[{"segment_id":"seg_001","start_ms":0,"end_ms":8000,'
        '"proposed_split_reason":"pause"}]}',
        encoding="utf-8",
    )
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "boundary_detection").write_text("", encoding="utf-8")
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "segment_classification").write_text("", encoding="utf-8")
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Precision oncology from circulating tumour cells.",
            "topics": [{"name": "liquid biopsy", "summary": "blood draw diagnostics"}],
        },
        skip_handoff=True,
    )
    (ctx.run_dir / ".stage_done" / "content_brief_reanchor").write_text("", encoding="utf-8")
    pending = pending_analysis_for_delivery(ctx)
    assert "source_topology_build" in pending
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "one_on_one_asymmetric", "speaker_stats": [{"speaker_id": "spk_0"}]},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {"topology_class": "one_on_one_asymmetric"},
        skip_handoff=True,
    )
    (ctx.run_dir / ".stage_done" / "source_topology_build").write_text("", encoding="utf-8")
    pending = pending_analysis_for_delivery(ctx)
    assert "framing_posture_decide" in pending
    assert "missing_framing" in pending
    assert "gap_framing_compose" in pending
    assert "delivery_brief_build" in pending


def test_pending_analysis_pins_content_context_when_brief_missing() -> None:
    """Brief hole after seg_resplit must pin content_context before missing_framing."""
    from interview_mux.homunculus.agenda import pending_analysis_for_delivery

    ctx = _ctx_010()
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "one_on_one_asymmetric", "speaker_stats": [{"speaker_id": "spk_0"}]},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {"topology_class": "one_on_one_asymmetric"},
        skip_handoff=True,
    )
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    for sid in (
        "source_topology_build",
        "boundary_detection",
        "segment_classification",
        "framing_posture_decide",
    ):
        (ctx.run_dir / ".stage_done" / sid).write_text("", encoding="utf-8")
    bpath = ctx.path("segments/boundaries.json")
    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(
        '{"boundaries":[{"segment_id":"seg_001","start_ms":0,"end_ms":8000,'
        '"proposed_split_reason":"pause"}]}',
        encoding="utf-8",
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "speaker_role": "interviewee",
                    "speaker_id": "spk_1",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest"],
                    "start_ms": 0,
                    "end_ms": 8000,
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/framing_posture_decision.json",
        {"posture": "hosted_interview", "rationale": "test"},
        skip_handoff=True,
    )
    assert not ctx.artifact_exists("understanding/content_brief.json")
    pending = pending_analysis_for_delivery(ctx)
    assert pending[0] == "content_context"
    assert "content_brief_reanchor" in pending
    assert pending.index("content_context") < pending.index("missing_framing")


def test_delivery_allows_content_context_when_brief_missing() -> None:
    """Classified tape must not block content_context when the brief is gone."""
    from interview_mux.homunculus.agenda import _refuse_delivery_timeline_rewind

    ctx = _ctx_010()
    _close_g0(ctx)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 8000,
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest"],
                }
            ]
        },
        skip_handoff=True,
    )
    assert not ctx.artifact_exists("understanding/content_brief.json")
    # Must not raise — allow producer re-run to restore the brief.
    _refuse_delivery_timeline_rewind(ctx, "content_context", action="run")



def test_pending_analysis_for_delivery_includes_stale_boundaries() -> None:
    """Stale boundaries must keep boundary_detection pending before SC (exec_10066)."""
    from interview_mux.homunculus.agenda import pending_analysis_for_delivery

    ctx = _ctx_010()
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "speaker_stats": [{"speaker_id": "spk_0"}],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {"topology_class": "one_on_one_asymmetric"},
        skip_handoff=True,
    )
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "source_topology_build").write_text("", encoding="utf-8")
    ctx.write_json(
        "segments/boundaries.json",
        {
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 8000,
                    "proposed_split_reason": "pause",
                }
            ],
            "_meta": {
                "producer_stage": "boundary_topic_resplit",
                "stale": True,
                "stale_reason": "invalidated_by:boundary_detection",
            },
        },
        skip_handoff=True,
    )
    (ctx.run_dir / ".stage_done" / "boundary_detection").write_text("", encoding="utf-8")
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "speaker_role": "interviewee",
                    "speaker_id": "spk_1",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest"],
                    "start_ms": 0,
                    "end_ms": 8000,
                }
            ]
        },
        skip_handoff=True,
    )
    (ctx.run_dir / ".stage_done" / "segment_classification").write_text("", encoding="utf-8")
    pending = pending_analysis_for_delivery(ctx)
    assert "boundary_detection" in pending
    # Stale BD must appear; SC may be absent if its own artifact looks complete.
    if "segment_classification" in pending:
        assert pending.index("boundary_detection") < pending.index(
            "segment_classification"
        )


def test_pending_analysis_for_delivery_restores_skipped_gap_artifacts() -> None:
    from interview_mux.homunculus.agenda import pending_analysis_for_delivery
    from interview_mux.stages.gaps import ensure_gap_fill_skipped

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "speaker_role": "interviewee",
                    "speaker_id": "spk_1",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest"],
                    "start_ms": 0,
                    "end_ms": 8000,
                }
            ]
        },
    )
    bpath = ctx.path("segments/boundaries.json")
    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(
        '{"boundaries":[{"segment_id":"seg_001","start_ms":0,"end_ms":8000,'
        '"proposed_split_reason":"pause"}]}',
        encoding="utf-8",
    )
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "boundary_detection").write_text("", encoding="utf-8")
    (ctx.run_dir / ".stage_done" / "segment_classification").write_text("", encoding="utf-8")
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Precision oncology from circulating tumour cells.",
            "topics": [{"name": "liquid biopsy", "summary": "blood draw diagnostics"}],
        },
        skip_handoff=True,
    )
    (ctx.run_dir / ".stage_done" / "content_brief_reanchor").write_text("", encoding="utf-8")
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "one_on_one_balanced", "speaker_stats": [{"speaker_id": "spk_0"}]},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {"topology_class": "one_on_one_balanced"},
        skip_handoff=True,
    )
    (ctx.run_dir / ".stage_done" / "source_topology_build").write_text("", encoding="utf-8")
    ensure_gap_fill_skipped(
        ctx, reason="low_frame_confidence", signals={"topology_class": "one_on_one_balanced"}
    )
    ctx.path("understanding", "gap_report.json").unlink(missing_ok=True)
    pending = pending_analysis_for_delivery(ctx)
    assert "missing_framing" not in pending
    assert "gap_framing_compose" not in pending
    assert ctx.artifact_exists("understanding/gap_report.json")
    assert "delivery_brief_build" in pending


def test_constrain_conductor_to_seed_front_blocks_missing_framing_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from interview_mux.homunculus.agenda import constrain_conductor_to_seed_front

    ctx = _ctx_010()
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.earliest_incomplete_seed_stage",
        lambda *_a, **_k: "framing_posture_decide",
    )
    remaining = [
        "framing_posture_decide",
        "boundary_topic_resplit",
        "missing_framing",
    ]
    assert constrain_conductor_to_seed_front(ctx, "analysis", remaining) == [
        "framing_posture_decide"
    ]


def test_seed_prereq_block_missing_framing_waits_on_framing_posture() -> None:
    from interview_mux.homunculus.runtime import _seed_prereq_block
    from interview_mux.v2.config import ANALYSIS_ORDER

    ctx = _ctx_010()
    upto = ANALYSIS_ORDER.index("framing_posture_decide")
    for sid in ANALYSIS_ORDER[:upto]:
        mark_done_raw(ctx, sid)
    assert _seed_prereq_block(ctx, "missing_framing") == "framing_posture_decide"


def test_seed_prereq_block_fresh_run_blocks_downstream_prepare() -> None:
    from interview_mux.homunculus.runtime import _seed_prereq_block

    ctx = _ctx_010()
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "run_mode": "partially-accelerated",
            "partial_auto": True,
        },
    )
    assert _seed_prereq_block(ctx, "ingest") is None
    assert _seed_prereq_block(ctx, "transcribe") == "ingest"
    assert _seed_prereq_block(ctx, "source_topology_build") == "ingest"


def test_seed_prereq_block_fresh_full_auto_waits_on_preclean() -> None:
    from interview_mux.homunculus.runtime import _seed_prereq_block

    ctx = _ctx_010()
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "run_mode": "full-auto",
            "full_auto": True,
        },
    )
    assert _seed_prereq_block(ctx, "ingest") == "audio_preclean"
    assert _seed_prereq_block(ctx, "source_topology_build") == "audio_preclean"


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
    assert not ctx.is_done("low_conf_island_scan")


def test_skip_source_topology_without_artifact_refused() -> None:
    from interview_mux.homunculus.agenda import skip_stage

    ctx = _ctx_010()
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, "source_topology_build", reason="conductor whim")
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "one_on_one_asymmetric", "speaker_stats": [{"speaker_id": "spk_0"}]},
    )
    ctx.write_json("understanding/flow_adaptation.json", {"topology_class": "one_on_one_asymmetric"})
    with pytest.raises(RuntimeError, match="speaker sample"):
        skip_stage(ctx, "source_topology_build", reason="missing samples")
    sample = ctx.path("understanding", "speaker_samples", "spk_0.wav")
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_bytes(b"RIFF" + b"\x00" * 64)
    doc = skip_stage(ctx, "source_topology_build", reason="already classified")
    assert "source_topology_build" in doc["skipped"]
    assert not ctx.is_done("source_topology_build")


def test_skip_core_analysis_stage_without_artifact_refused() -> None:
    from interview_mux.homunculus.agenda import skip_stage

    ctx = _ctx_010()
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, "ideal_cuts_propose", reason="coverage miss")
    ctx.path("understanding/ideal_cuts.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("understanding/ideal_cuts.json").write_text('{"cuts": [{"cut_id": "c1"}]}', encoding="utf-8")
    doc = skip_stage(ctx, "ideal_cuts_propose", reason="already proposed")
    assert "ideal_cuts_propose" in doc["skipped"]
    assert not ctx.is_done("ideal_cuts_propose")


def test_skip_transitions_without_artifact_refused() -> None:
    from interview_mux.homunculus.agenda import skip_stage

    ctx = _ctx_010()
    with pytest.raises(RuntimeError, match="cannot skip transitions"):
        skip_stage(
            ctx,
            "transitions",
            reason="exclusion conflicts",
            compensating_fact="67b9d444",
        )
    ctx.write_json("master/transitions.json", {"transitions": []}, skip_handoff=True)
    doc = skip_stage(ctx, "transitions", reason="empty bridges ok")
    assert "transitions" in doc["skipped"]
    assert not ctx.is_done("transitions")


def test_walk_seed_agenda_runs_hollow_skipped_transitions(monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.homunculus.agenda import walk_seed_agenda, write_agenda

    ctx = _ctx_010()
    plant_seed_complete_through(ctx, "air_contract_sanitize")
    _plant_theme_wavs(ctx)
    tr = ctx.final_path("master", "transitions.json")
    if tr.is_file():
        tr.unlink()
    write_agenda(ctx, "delivery", ["transitions", "sound_design_plan"], source="test")
    ctx.write_json(
        "mastering/homunculus/agenda.json",
        {
            "phase": "delivery",
            "remaining": ["transitions", "sound_design_plan"],
            "source": "conductor",
            "seed_order": [],
            "skipped": ["transitions"],
            "scheduled": [],
            "reruns": [],
        },
    )
    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage",
        lambda _ctx, stage: ran.append(stage),
    )
    walk_seed_agenda(ctx, ["transitions", "sound_design_plan"], reason="test")
    assert ran[0] == "transitions"
    agenda = ctx.read_json("mastering/homunculus/agenda.json")
    assert "transitions" not in (agenda.get("skipped") or [])


def test_skip_vo_synthesize_refused_when_pairs_missing() -> None:
    from interview_mux.homunculus.agenda import skip_stage
    from interview_mux.vo_synthesis_audit import record_synthesis

    ctx = _ctx_010()
    text = "Meanwhile the trial enrolled."
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_055",
                    "before_segment_id": "seg_058",
                    "text": text,
                    "type": "bridge",
                }
            ]
        },
        skip_handoff=True,
    )
    with pytest.raises(RuntimeError, match="cannot skip vo_synthesize"):
        skip_stage(ctx, "vo_synthesize", reason="conductor whim")
    ctx.write_json(
        "mastering/vo_synthesize.json",
        {"version": 1, "still_missing_pairs": []},
        skip_handoff=True,
    )
    dest = ctx.path("master", "transitions")
    dest.mkdir(parents=True, exist_ok=True)
    import wave

    wav = dest / "tr_seg_055_seg_058.wav"
    with wave.open(str(wav), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * 4800)
    record_synthesis(
        ctx,
        {
            "line_id": "tr_seg_055_seg_058",
            "text": text,
            "after_segment_id": "seg_055",
            "before_segment_id": "seg_058",
        },
        backend="mlx_audio",
        out_wav=wav,
    )
    doc = skip_stage(ctx, "vo_synthesize", reason="pairs on disk")
    assert "vo_synthesize" in doc["skipped"]
    assert not ctx.is_done("vo_synthesize")


def test_refuse_music_before_assembly() -> None:
    from interview_mux.homunculus.agenda import (
        _refuse_music_before_assembly,
        skip_stage,
    )
    from interview_mux.homunculus.runtime import dispatch_stage

    ctx = _ctx_010()
    refuse_copy = r"assembly_missing|HAU requires seated assembly"
    with pytest.raises(RuntimeError, match=refuse_copy):
        skip_stage(ctx, "music_palette_compose", reason="conductor whim")
    with pytest.raises(RuntimeError, match=refuse_copy):
        _refuse_music_before_assembly(ctx, "sfx_prompt_craft", action="run")
    ran = []
    with pytest.raises(RuntimeError, match=refuse_copy):
        dispatch_stage(ctx, "music_palette_compose", lambda: ran.append("ran"), source="conductor")
    assert ran == []
    assert not ctx.is_done("music_palette_compose")
    plant_seed_complete_through(ctx, "mix")
    _plant_theme_wavs(ctx)
    _commit_assembly(ctx)
    _open_preview_music(ctx)
    _refuse_music_before_assembly(ctx, "music_palette_compose", action="run")


def test_skip_mmaudio_refused_when_theme_wavs_missing() -> None:
    from interview_mux.homunculus.agenda import skip_stage

    ctx = _ctx_010()
    dest = ctx.path("understanding/sound_design_plan.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "asset_id": "show_theme_v1_motif",
                        "role": "theme_cold_open",
                        "duration_seconds": 12,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="cannot skip mmaudio_sfx"):
        skip_stage(ctx, "mmaudio_sfx", reason="conductor whim")
    wav = ctx.path("sound_design", "assets", "show_theme_v1_motif.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    with pytest.raises(RuntimeError, match="cannot skip mmaudio_sfx"):
        skip_stage(ctx, "mmaudio_sfx", reason="theme wav on disk")


def test_mmaudio_empty_qa_is_not_present() -> None:
    from interview_mux.homunculus.agenda import skip_stage, stage_outputs_present

    ctx = _ctx_010()
    dest = ctx.path("understanding/sound_design_plan.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"assets": [{"asset_id": "show_theme_v1_motif", "role": "theme_cold_open"}]}), encoding="utf-8")
    preview = ctx.path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\x00" * 64)
    wav = ctx.path("sound_design", "assets", "show_theme_v1_motif.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    qa = ctx.path("sound_design", "mmaudio_qa.json")
    qa.write_text(json.dumps({"version": 1, "assets": []}), encoding="utf-8")
    assert stage_outputs_present(ctx, "mmaudio_sfx") is False
    with pytest.raises(RuntimeError, match="cannot skip mmaudio_sfx"):
        skip_stage(ctx, "mmaudio_sfx", reason="empty qa file exists")


def test_edl_resume_does_not_rewind_layup(monkeypatch) -> None:
    """from_stage=edl must not pull unmarked nugget_layup_compose back into the walk."""
    from interview_mux.homunculus.agenda import AGENDA_REL, run_homunculus_phase

    ctx = _ctx_010()
    plant_seed_complete_through(ctx, "edl_narrative_audit")
    _plant_theme_wavs(ctx)
    for rel in (
        "segments/boundaries.json",
        "segments/manifest.json",
        "understanding/content_brief.json",
        "understanding/gap_evaluations.json",
        "understanding/gap_report.json",
        "understanding/delivery_brief.json",
        "understanding/source_topology.json",
    ):
        dest = ctx.path(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file():
            dest.write_text("{}", encoding="utf-8")
    walked: list[tuple[str, tuple[str, ...]]] = []

    def _walk(_ctx, stages, *, reason: str) -> None:
        walked.append((reason, tuple(stages)))
        for sid in stages:
            mark_done_raw(_ctx, sid)

    monkeypatch.setattr("interview_mux.homunculus.agenda.walk_seed_agenda", _walk)
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.pending_analysis_for_delivery",
        lambda _c: [],
    )
    run_homunculus_phase(ctx, "delivery", ["edl", "mix"], client=_stop_client())
    walked_ids = [sid for _reason, stages in walked for sid in stages]
    assert "nugget_layup_compose" not in walked_ids
    assert "sound_design_plan" not in walked_ids
    agenda = ctx.read_json(AGENDA_REL) if ctx.artifact_exists(AGENDA_REL) else {}
    remaining = [str(s) for s in (agenda.get("remaining") or [])]
    assert "nugget_layup_compose" not in remaining
    assert "edl" in remaining or walked_ids[:1] == ["edl"] or "edl" in walked_ids


def test_mix_outputs_absent_when_assembly_older_than_edl() -> None:
    import os
    import time

    from interview_mux.homunculus.agenda import remaining_stages, stage_outputs_present

    ctx = _ctx_010()
    plant_seed_complete_through(ctx, "edl")
    _plant_theme_wavs(ctx)
    asm = ctx.final_path("master", "assembly.wav")
    edl = ctx.final_path("master", "edl.json")
    now = time.time()
    os.utime(asm, (now - 30, now - 30))
    os.utime(edl, (now, now))
    assert stage_outputs_present(ctx, "mix") is False
    assert stage_outputs_present(ctx, "junction_snip_qa") is False
    assert stage_outputs_present(ctx, "master_finalize") is False
    assert "mix" in remaining_stages(ctx, "delivery")
    payload = asm.read_bytes()
    autopsy = ctx.final_path("master", "seam_autopsy.json")
    autopsy.write_text(
        json.dumps(
            {
                "version": 1,
                "commitment": {
                    "status": "committed",
                    "assembly": {"exists": True, "size": len(payload)},
                    "reasons": [],
                },
            }
        ),
        encoding="utf-8",
    )
    os.utime(asm, (now + 30, now + 30))
    os.utime(edl, (now - 20, now - 20))
    os.utime(autopsy, (now - 10, now - 10))
    _open_preview_music(ctx)
    # Mtime-fresh assembly is not enough; mix stays hollow until generation commitment.
    if stage_outputs_present(ctx, "mix"):
        assert "mix" not in remaining_stages(ctx, "delivery")
    else:
        assert "mix" in remaining_stages(ctx, "delivery")
    assert stage_outputs_present(ctx, "junction_snip_qa") is False
    assert "junction_snip_qa" in remaining_stages(ctx, "delivery")


def test_junction_outputs_present_when_commitment_matches_touched_assembly() -> None:
    """exec_5404: assembly mtime bump alone must not hollow a committed autopsy."""
    import json
    import os
    import time

    from interview_mux.homunculus.agenda import stage_outputs_present

    ctx = _ctx_010()
    plant_seed_complete_through(ctx, "edl")
    _plant_theme_wavs(ctx)
    asm = ctx.final_path("master", "assembly.wav")
    edl = ctx.final_path("master", "edl.json")
    autopsy = ctx.final_path("master", "seam_autopsy.json")
    payload = asm.read_bytes()
    write_fixture_json(
        ctx,
        "master/junction_snip_qa.json",
        {"schema_version": 1, "status": "pass", "seams": []},
    )
    autopsy.write_text(
        json.dumps(
            {
                "version": 1,
                "commitment": {
                    "status": "committed",
                    "assembly": {"exists": True, "size": len(payload)},
                    "reasons": [],
                },
            }
        ),
        encoding="utf-8",
    )
    now = time.time()
    os.utime(edl, (now - 90, now - 90))
    os.utime(autopsy, (now - 60, now - 60))
    os.utime(asm, (now, now))
    assert stage_outputs_present(ctx, "junction_snip_qa") is True


def test_edl_outputs_absent_when_selection_order_drifted() -> None:
    from interview_mux.homunculus.agenda import stage_outputs_present
    from interview_mux.order_hash import stamp_order_hash

    import json

    ctx = _ctx_010()
    sel = stamp_order_hash({"ordered_segment_ids": ["seg_001", "seg_002", "seg_003"]})
    edl = stamp_order_hash(
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "clips": [
                {"type": "speech", "segment_id": "seg_001"},
                {"type": "speech", "segment_id": "seg_002"},
            ],
        }
    )
    for rel, doc in (("master/selection.json", sel), ("master/edl.json", edl)):
        dest = ctx.path(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(doc), encoding="utf-8")
    assert stage_outputs_present(ctx, "edl") is False


def test_layup_freshness_does_not_hollow_present_plan() -> None:
    """Selection-order heals must not treat a present layup plan as missing output."""
    from interview_mux.homunculus.agenda import stage_outputs_present

    ctx = _ctx_010()
    dest = ctx.path("understanding/nugget_layup_plan.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("{}", encoding="utf-8")
    assert dest.is_file()
    assert stage_outputs_present(ctx, "nugget_layup_compose") is True


def test_unmark_hollow_heals_empty_mmaudio_qa_when_wavs_exist(monkeypatch) -> None:
    from interview_mux.homunculus.agenda import (
        stage_outputs_present,
        unmark_hollow_delivery_producers,
    )

    ctx = _ctx_010()
    plant_seed_complete_through(ctx, "sound_design_plan")
    write_fixture_json(
        ctx,
        "understanding/sound_design_plan.json",
        {
            "assets": [
                {"asset_id": "show_theme_v1_motif", "role": "theme_cold_open"}
            ],
            "_meta": {"producer_stage": "sound_design_plan"},
        },
    )
    _plant_theme_wavs(ctx)
    _commit_assembly(ctx)
    _open_preview_music(ctx)
    write_fixture_theme_wav(ctx, "sound_design/assets/show_theme_v1_motif.wav")
    qa = ctx.path("sound_design", "mmaudio_qa.json")
    qa.write_text(json.dumps({"version": 1, "assets": []}), encoding="utf-8")
    mark_done_raw(ctx, "mmaudio_sfx")

    def _heal(_ctx) -> dict:
        write_fixture_json(
            _ctx,
            "sound_design/mmaudio_qa.json",
            {
                "version": 1,
                "assets": [{"asset_id": "show_theme_v1_motif", "verdict": "pass"}],
            },
        )
        return {"healed": True, "dropped": [], "analyzed": ["show_theme_v1_motif"]}

    monkeypatch.setattr(
        "interview_mux.mmaudio_asset_qa.heal_mmaudio_qa_wav_parity",
        _heal,
    )
    cleared = unmark_hollow_delivery_producers(ctx, {"mmaudio_sfx"})
    assert cleared == []
    assert ctx.is_done("mmaudio_sfx")
    assert stage_outputs_present(ctx, "mmaudio_sfx") is True


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
    _mark_analysis_prefix(ctx, "speaker_roles")
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
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9}
            ]
        },
        skip_handoff=True,
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
    _mark_analysis_prefix(ctx, "transcribe")
    ran: list[str] = []

    def _impl() -> None:
        ran.append("ran")
        ctx.write_json("transcript/full.json", {"text": "fresh tape"})

    dispatch_stage(ctx, "transcribe", _impl, source="conductor")
    assert ran == ["ran"]


def test_hollow_transcribe_done_is_unmarked_and_run() -> None:
    from interview_mux.homunculus.agenda import unmark_hollow_prepare_stages

    ctx = _ctx_010()
    prov = ctx.path("preclean", "provider.json")
    prov.parent.mkdir(parents=True, exist_ok=True)
    prov.write_text('{"status":"skipped","provider":"fixture"}', encoding="utf-8")
    wav = ctx.path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    mark_done_raw(ctx, "audio_preclean", "ingest")
    # Hollow transcribe only (done marker, no transcript artifact).
    done = ctx.final_path(".stage_done", "transcribe")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("", encoding="utf-8")
    cleared = unmark_hollow_prepare_stages(ctx)
    assert "transcribe" in cleared
    assert not ctx.is_done("transcribe")
    assert ctx.is_done("ingest")
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


def test_apply_pack_always_keeps_gap_framing_host_packet() -> None:
    from interview_mux.homunculus.packer import apply_pack_to_kwargs

    ctx = _ctx_010()
    host = json.dumps(
        {
            "gap_evaluations": {"evaluations": [{"segment_id": "seg_001"}]},
            "gap_framing_policy": {"min_vo_insert_ratio": 0.08},
            "prior_native_contexts": {"seg_001": {"segment_id": "seg_000"}},
        }
    )
    out = apply_pack_to_kwargs(
        ctx,
        "gap_framing_compose",
        {"messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": host}]},
    )
    user = " ".join(str(m.get("content")) for m in out["messages"] if m.get("role") == "user")
    assert "--- stage input ---" not in user
    assert "prior_native_contexts" in user
    assert "gap_evaluations" in user
    assert user.strip().startswith("{")


def test_apply_pack_prefers_stage_json_over_prior_native_turns() -> None:
    """Prior-beat volley turns must not replace missing_framing / gap compose JSON."""
    from interview_mux.homunculus.packer import apply_pack_to_kwargs

    ctx = _ctx_010()
    host = json.dumps(
        {
            "segments": {
                "segments": [
                    {
                        "segment_id": "seg_002",
                        "speaker_role": "interviewee",
                        "text": "guest answer text " + ("x" * 80),
                    }
                ]
            },
            "content_brief": {"thesis": "guest story"},
        }
    )
    prior = (
        "PRIOR NATIVE BEATS (immediate previous ordered segments before VO targets).\n"
        "still use prior_native_contexts in the stage input JSON.\n"
        + ("y" * 80)
    )
    out = apply_pack_to_kwargs(
        ctx,
        "missing_framing",
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": prior},
                {"role": "assistant", "content": "Understood."},
                {"role": "user", "content": "Now write the gap framing interviewer_lines."},
                {"role": "user", "content": host},
            ]
        },
    )
    user = " ".join(str(m.get("content")) for m in out["messages"] if m.get("role") == "user")
    assert "seg_002" in user
    assert "guest answer text" in user
    assert "PRIOR NATIVE BEATS" not in user
    assert user.strip().startswith("{")


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
    _mark_analysis_prefix(ctx, "boundary_detection")
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


def test_pack_conductor_context_includes_prereqs_and_readiness() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "speaker_role": "interviewee",
                    "speaker_id": "spk_1",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest"],
                    "start_ms": 0,
                    "end_ms": 8000,
                }
            ]
        },
    )
    from interview_mux.homunculus.packer import pack_conductor_context

    blob = pack_conductor_context(ctx)
    assert "delivery_analysis_prereqs" in blob
    assert "resolve_stage_plan" in blob
    assert "delivery_readiness" in blob
    assert "source_topology_build" in blob


def test_hollow_skip_blocked_returns_structured_payload() -> None:
    from interview_mux.homunculus.agenda import HollowSkipBlockedError, skip_stage

    ctx = _ctx_010()
    mark_done_raw(ctx, "vo_line_adjudicate")
    with pytest.raises(HollowSkipBlockedError) as exc_info:
        skip_stage(ctx, "vo_line_adjudicate", reason="conductor whim")
    payload = exc_info.value.payload
    assert payload["ok"] is False
    assert payload["reason"] == "hollow_done"
    assert payload["stage"] == "vo_line_adjudicate"
    assert payload["action"] == "unmark_and_rerun_once"
    assert "skip_stage" in payload["do_not"]
    assert not ctx.is_done("vo_line_adjudicate")


def test_hollow_skip_escalates_to_needs_operator() -> None:
    from interview_mux.homunculus.agenda import HollowSkipBlockedError, skip_stage

    ctx = _ctx_010()
    mark_done_raw(ctx, "framing_posture_decide")
    with pytest.raises(HollowSkipBlockedError) as exc_info:
        skip_stage(ctx, "framing_posture_decide", reason="first")
    assert exc_info.value.payload["action"] == "unmark_and_rerun_once"
    mark_done_raw(ctx, "framing_posture_decide")
    with pytest.raises(HollowSkipBlockedError) as exc_info:
        skip_stage(ctx, "framing_posture_decide", reason="second")
    payload = exc_info.value.payload
    assert payload["action"] == "needs_operator"
    assert payload["attempt"] >= 2
    assert ctx.artifact_exists("mastering/homunculus/plan.json")
    meta = ctx.read_json("run_meta.json")
    assert meta.get("needs_operator") is True


def test_unmark_hollow_includes_new_stages() -> None:
    from interview_mux.homunculus.agenda import unmark_hollow_delivery_producers

    ctx = _ctx_010()
    mark_done_raw(ctx, "vo_line_adjudicate")
    cleared = unmark_hollow_delivery_producers(ctx, {"vo_line_adjudicate"})
    assert "vo_line_adjudicate" in cleared
    assert not ctx.is_done("vo_line_adjudicate")


def test_order_change_invalidates_nugget_layup(tmp_path: Path) -> None:
    from interview_mux.air_order_integrity import on_selection_order_changed
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "hom_order_inv")
    layup = ctx.path("understanding", "nugget_layup_plan.json")
    layup.parent.mkdir(parents=True, exist_ok=True)
    layup.write_text(
        json.dumps({"version": 1, "layups": [], "ordered_segment_ids": []}),
        encoding="utf-8",
    )
    done = ctx.final_path(".stage_done", "nugget_layup_compose")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("", encoding="utf-8")
    prev = {"ordered_segment_ids": ["seg_a", "seg_b"]}
    cur = {"ordered_segment_ids": ["seg_b", "seg_a"]}
    notes = on_selection_order_changed(ctx, source="test", previous=prev, current=cur)
    assert "invalidated_downstream:nugget_layup_compose" in notes
    assert not ctx.is_done("nugget_layup_compose")


@pytest.mark.real_executions_root  # test supplies its own INTERVIEW_MUX_ROOT
def test_homunculus_skip_stage_api_hollow_done(tmp_path, monkeypatch) -> None:
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
    ok = client.post(
        "/api/runs",
        json={"input_audio_path": "ASSETS/input/interview.wav", "run_mode": "manual"},
    )
    assert ok.status_code == 200, ok.text
    run_id = ok.json()["run_id"]
    run_dir = assets / "executions" / run_id
    done = run_dir / ".stage_done" / "vo_line_adjudicate"
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("", encoding="utf-8")
    resp = client.post(
        f"/api/runs/{run_id}/homunculus/skip-stage",
        json={"stage": "vo_line_adjudicate", "reason": "gui probe"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("reason") == "hollow_done"
    assert body.get("ok") is False
    assert "operator_card" in body

