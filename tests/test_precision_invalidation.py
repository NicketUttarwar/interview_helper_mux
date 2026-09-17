"""p15-precision-invalidate (§5.4): invalidate consumers, not the whole tail.

`transitive_invalidate()` returned every stage after the source, so one stale
artifact reopened the pipeline — the ~49 backward-rewind excess dispatches of
§5.1. Precision subtracts from that tail, and every test here exists to pin the
direction of the risk: **over-invalidation wastes work, under-invalidation ships a
master built from stale parts.** So the invariants are one-sided on purpose.

The near-miss these tests encode: `audio_probe_build` is conformance-green and its
contract names four consumers, but `content_context`, `talking_points_compose` and
`ideal_cuts_propose` all read its `transcript/protected_zones.json` through
`stage_input_helpers.transcript_quality_for_ctx`, which no contract mentions. A
gate that only asked about the *source* would have dropped them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux import artifact_dependency_graph as adg
from interview_mux import master_epoch
from interview_mux.context_resolver import ARTIFACTS_REGISTRY
from interview_mux.homunculus.budget import AUDIO_MUTATING
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import isolated_run_ctx

ALL_STAGES = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)

# Stages that read `transcript/protected_zones.json` via
# `stage_input_helpers.transcript_quality_for_ctx` without declaring it.
UNDECLARED_PROBE_CONSUMERS = ("content_context", "talking_points_compose", "ideal_cuts_propose")


@pytest.fixture(autouse=True)
def _fresh_graph():
    adg.build_graph.cache_clear()
    yield
    adg.build_graph.cache_clear()


def _ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto", "full_auto": True},
        skip_handoff=True,
    )
    return ctx


# ---------------------------------------------------------------------------
# Inertness today, and the one-sided invariant forever
# ---------------------------------------------------------------------------

def test_precision_is_inert_today() -> None:
    """No group downstream of `prepare` is conformance-green, so nothing is dropped."""
    for sid in ALL_STAGES:
        assert adg.transitive_invalidate(sid) == adg._blanket_invalidate(sid), sid


def test_precise_result_is_always_a_subsequence_of_the_blanket_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Precision may only subtract, and may not reorder — callers iterate this list.

    Checked with the strict-group ratchet wound forward, because the invariant has
    to hold for the groups that have not flipped yet too.
    """
    for strict in ("prepare", "prepare,understand-a", "prepare,understand-a,understand-b"):
        monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", strict)
        for sid in ALL_STAGES:
            blanket = adg._blanket_invalidate(sid)
            precise = adg.transitive_invalidate(sid)
            assert set(precise) <= set(blanket), f"{sid} invalidates MORE than today"
            assert precise == [s for s in blanket if s in set(precise)], f"{sid} reordered"


def test_the_mechanism_is_live_not_dead_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wind the ratchet forward and precision must actually subtract something."""
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", "prepare,understand-a,understand-b")
    shrunk = {
        sid: len(adg._blanket_invalidate(sid)) - len(adg.transitive_invalidate(sid))
        for sid in ALL_STAGES
    }
    assert any(v > 0 for v in shrunk.values()), "precision never narrows anything"


def test_kill_switch_restores_blanket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", "prepare,understand-a,understand-b")
    monkeypatch.setenv("MUX_PRECISION_INVALIDATE", "0")
    assert not adg.precision_invalidate_enabled()
    for sid in ALL_STAGES:
        assert adg.transitive_invalidate(sid) == adg._blanket_invalidate(sid), sid


# ---------------------------------------------------------------------------
# The two-sided gate
# ---------------------------------------------------------------------------

def test_an_ungreen_consumer_is_never_dropped() -> None:
    """The near-miss: undeclared readers of a green stage's output stay invalidated."""
    kept = adg.transitive_invalidate("audio_probe_build")
    for sid in UNDECLARED_PROBE_CONSUMERS:
        assert not adg.precision_droppable(sid), f"{sid} is not conformance-green yet"
        assert sid in kept, f"{sid} reads protected_zones.json and must stay invalidated"


def test_droppability_requires_the_consumers_own_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dropping a stage is a claim about ITS inputs, so it needs ITS green group."""
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", "prepare")
    assert not adg.precision_droppable("content_context")
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", "prepare,understand-a")
    assert adg.precision_droppable("content_context")


def test_a_stage_with_an_unknown_input_producer_is_never_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", "prepare,understand-a,understand-b")
    for sid in ALL_STAGES:
        producers = adg._input_producers(sid)
        if not producers or not any(p is None for p in producers):
            continue
        # Unknown producer ⇒ unknown dependency ⇒ present in every invalidation
        # set that reaches it.
        for source in ALL_STAGES:
            blanket = adg._blanket_invalidate(source)
            if sid in blanket:
                assert sid in adg.transitive_invalidate(source), f"{sid} dropped by {source}"


# ---------------------------------------------------------------------------
# Hollow contracts, and the audio rail
# ---------------------------------------------------------------------------

def test_a_hollow_contract_never_means_nothing_downstream_cares(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No declared edges ⇒ ineligible ⇒ whole tail. Never an empty precise set."""
    monkeypatch.setenv(
        "MUX_CONTRACT_STRICT_GROUPS",
        "prepare,understand-a,understand-b,understand-c,fill_gaps,plan_rank,sound,build,ship",
    )
    hollow = [sid for sid in ALL_STAGES if not adg.declared_downstream(sid)]
    assert hollow, "fixture assumes some contracts are still hollow"
    for sid in hollow:
        assert not adg.precision_eligible(sid), f"{sid} is hollow but went precise"
        assert adg.transitive_invalidate(sid) == adg._blanket_invalidate(sid), sid


def test_a_stage_with_no_declared_inputs_is_never_droppable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MUX_CONTRACT_STRICT_GROUPS",
        "prepare,understand-a,understand-b,understand-c,fill_gaps,plan_rank,sound,build,ship",
    )
    for sid in ALL_STAGES:
        if adg._input_producers(sid):
            continue
        assert not adg.precision_droppable(sid), f"{sid} declares no inputs but is droppable"


def test_audio_stages_stay_whole_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan §5.4 rail 1, both directions: never a precise source, never dropped."""
    monkeypatch.setenv(
        "MUX_CONTRACT_STRICT_GROUPS",
        "prepare,understand-a,understand-b,understand-c,fill_gaps,plan_rank,sound,build,ship",
    )
    for sid in sorted(AUDIO_MUTATING):
        if sid not in ALL_STAGES:
            continue  # host identities (run_musicgen etc.) are not pipeline stages
        assert adg.audio_touching(sid)
        assert not adg.precision_eligible(sid), sid
        assert not adg.precision_droppable(sid), sid
        assert adg.transitive_invalidate(sid) == adg._blanket_invalidate(sid), sid


def test_no_audio_stage_is_precision_proven_without_a_fixture() -> None:
    """`_AUDIO_PRECISION_PROVEN` may only grow together with a superset fixture."""
    assert adg._AUDIO_PRECISION_PROVEN == frozenset()


# ---------------------------------------------------------------------------
# Monotonicity — populating a contract may only widen invalidation
# ---------------------------------------------------------------------------

def test_declared_downstream_covers_the_registry_consumer_set() -> None:
    """Contract `consumers` is unioned with the registry, never substituted for it."""
    for stage, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        registry_consumers = {
            cons for cons, paths in ARTIFACTS_REGISTRY.items() if rel in paths
        } - {stage}
        declared = set(adg.declared_downstream(stage))
        assert registry_consumers <= declared, stage


def test_contract_propagation_only_adds_to_the_legacy_seeds() -> None:
    """`propagation_map()` is read at import time by `artifact_root_cause`."""
    live = adg.propagation_map()
    for stage, seeds in adg._PROPAGATION_SEEDS.items():
        assert set(seeds) <= set(live.get(stage) or ()), stage


def test_turning_on_contract_requires_only_widens_declared_downstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    off = {sid: set(adg.declared_downstream(sid)) for sid in ALL_STAGES}
    monkeypatch.setenv("MUX_CONTRACT_REQUIRES", "1")
    adg.build_graph.cache_clear()
    on = {sid: set(adg.declared_downstream(sid)) for sid in ALL_STAGES}
    for sid in ALL_STAGES:
        assert off[sid] <= on[sid], sid


# ---------------------------------------------------------------------------
# Epoch assertion at the seal (rail 2)
# ---------------------------------------------------------------------------

def _write_master(ctx: RunContext, body: bytes = b"RIFFmaster") -> Path:
    dest = ctx.final_path("master", "master.wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return dest


def test_epoch_starts_at_zero_and_bumps_on_invalidation(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "epoch_bump")
    assert master_epoch.current_epoch(ctx.run_dir) == 0
    assert master_epoch.record_invalidation(ctx, "edl", ["mix", "master_finalize"]) == 1
    assert master_epoch.record_invalidation(ctx, "mix", ["master_finalize"]) == 2
    assert master_epoch.current_epoch(ctx.run_dir) == 2


def test_a_master_that_predates_a_master_path_invalidation_fails(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "epoch_stale")
    master = _write_master(ctx)
    master_epoch.record_invalidation(ctx, "edl", ["edl", "mix", "master_finalize"])
    failures = master_epoch.epoch_failures(master)
    assert failures and "predates invalidation epoch" in failures[0]


def test_a_master_rebuilt_after_the_invalidation_passes(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "epoch_rebuilt")
    master = _write_master(ctx)
    master_epoch.record_invalidation(ctx, "edl", ["edl", "mix"])
    _write_master(ctx, b"RIFFmaster-rebuilt-with-different-length")
    assert master_epoch.epoch_failures(master) == []


def test_an_invalidation_off_the_master_path_does_not_fail_the_seal(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "epoch_offpath")
    master = _write_master(ctx)
    master_epoch.record_invalidation(ctx, "content_context", ["boundary_detection"])
    assert master_epoch.epoch_failures(master) == []


def test_no_epoch_record_means_no_opinion(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "epoch_absent")
    assert master_epoch.epoch_failures(_write_master(ctx)) == []


def test_epoch_assertion_can_be_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, "epoch_disabled")
    master = _write_master(ctx)
    master_epoch.record_invalidation(ctx, "edl", ["edl", "mix"])
    monkeypatch.setenv("MUX_MASTER_EPOCH_ASSERT", "0")
    assert master_epoch.epoch_failures(master) == []


def test_verify_master_reports_the_epoch_and_refuses_a_stale_master(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import master_qc

    ctx = _ctx(tmp_path, "epoch_verify")
    master = _write_master(ctx)
    monkeypatch.setattr(
        master_qc,
        "_collect_metrics",
        lambda _p: master_qc.MasterMetrics(
            duration_seconds=120.0,
            sample_rate_hz=48000,
            channels=2,
            integrated_lufs=-16.0,
            true_peak_dbtp=-1.2,
        ),
    )
    clean = master_qc.verify_master(master, flow="podcast")
    assert clean.ok is True
    assert any(c.startswith("invalidation_epoch=") for c in clean.checks)

    master_epoch.record_invalidation(ctx, "mix", ["mix", "master_finalize"])
    stale = master_qc.verify_master(master, flow="podcast")
    assert stale.ok is False
    assert any("predates invalidation epoch" in f for f in stale.failures)


def test_the_real_invalidation_path_stamps_the_epoch(tmp_path: Path) -> None:
    """`RunContext.clear_from` funnels through `invalidate_downstream_memory`."""
    from interview_mux.artifact_lifecycle import invalidate_downstream_memory

    ctx = _ctx(tmp_path, "epoch_wired")
    invalidate_downstream_memory(ctx, "edl")
    doc = master_epoch.read_epoch(ctx.run_dir)
    assert doc.get("epoch") == 1
    event = doc.get("last_event") or {}
    assert event.get("from_stage") == "edl"
    assert event.get("master_path") is True
    assert event.get("mode") in {"blanket", "precise"}
