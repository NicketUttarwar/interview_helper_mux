"""Precision invalidation may not drop a stage on the strength of an ABSENCE.

Plan `.cursor/plans/solver_brain_020.plan.md` §3.4 argued `propagation` /
`consumers` population was safe because the blast radius "can only widen". §5.4
ended that: precision invalidation clamps the invalidation set to a subsequence
of the blanket set, driven by exactly those two fields, so they are now
**subtractive** — declaring them can REMOVE a stage from the set.

That makes an under-declared edge list the dangerous direction. It no longer
fails safe; it strands a stale artifact in a downstream stage that should have
been re-run, and the run finishes on it silently.

So the precondition these tests pin is: **empty is not none.** A stage may only
leave an invalidation set when something affirmatively says its edges are
complete. Absent edge data means *unknown*, and unknown keeps the whole tail.
A contract with genuinely no consumers says so out loud —
`edges: {consumers: terminal}` — and only then is the empty list believed.

The live case: `framing_posture_decide` declares three inputs, no contract
anywhere names it as a consumer, and `framing_posture.build_framing_posture_input`
reads `understanding/content_brief.json`, `segments/manifest.json` and
`understanding/ideal_cuts_materialized.json` — none of them declared. Before this
precondition it was dropped from **8** invalidation sets, every one of which was
still re-running a producer of something it really reads.
"""

from __future__ import annotations

import dataclasses

import pytest

from interview_mux import artifact_dependency_graph as adg
from interview_mux.homunculus.budget import AUDIO_MUTATING
from interview_mux.master_epoch import MASTER_PATH_STAGES
from interview_mux.stage_contract import load_contract
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

ALL_STAGES = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
ALL_GROUPS = "prepare,understand-a,understand-b,understand-c,fill_gaps,plan_rank,sound,build,ship"

# Nobody declares this stage downstream of anything, and it reads three artifacts
# its contract never mentions. Both halves are asserted below rather than assumed.
UNWITNESSED = "framing_posture_decide"
UNDECLARED_READS = (
    "understanding/content_brief.json",
    "segments/manifest.json",
    "understanding/ideal_cuts_materialized.json",
)


@pytest.fixture(autouse=True)
def _fresh_graph():
    adg.build_graph.cache_clear()
    yield
    adg.build_graph.cache_clear()


def _patch_contract(monkeypatch: pytest.MonkeyPatch, stage_id: str, contract) -> None:
    real = load_contract

    def _patched(sid: str):
        return contract if sid == stage_id else real(sid)

    monkeypatch.setattr("interview_mux.artifact_dependency_graph.load_contract", _patched)
    adg.build_graph.cache_clear()


def _producers_of(rel: str) -> set[str]:
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
    from interview_mux.stage_contract import all_contract_stage_ids

    out = {sid for sid, path in STAGE_ARTIFACT_DISK_PATHS.items() if path == rel}
    for sid in all_contract_stage_ids():
        contract = load_contract(sid)
        if contract and any(o.path == rel for o in contract.outputs):
            out.add(sid)
    return out


# ---------------------------------------------------------------------------
# (a) Undeclared / empty consumer edges are never read as "safe to drop"
# ---------------------------------------------------------------------------

def test_the_premise_a_stage_can_read_what_no_contract_declares() -> None:
    """If this ever fails the fixture is stale, not the precondition."""
    from interview_mux import framing_posture

    with open(framing_posture.__file__, encoding="utf-8") as fh:
        body = fh.read()
    contract = load_contract(UNWITNESSED)
    assert contract is not None
    declared = {i.path for i in contract.inputs}
    for rel in UNDECLARED_READS:
        assert rel in body, f"{UNWITNESSED} no longer reads {rel}"
        assert rel not in declared, f"{rel} is declared now — re-measure the hazard"


def test_an_unwitnessed_stage_is_never_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """No upstream contract names it ⇒ its inbound edges are unknown ⇒ keep it.

    Wound all the way forward, because the hazard arms progressively as groups
    flip to conformance-strict.
    """
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", ALL_GROUPS)
    assert adg.declared_upstream(UNWITNESSED) == (), "fixture assumes nobody declares it"
    assert not adg.contract_edges_complete(UNWITNESSED)
    assert not adg.precision_droppable(UNWITNESSED)

    producers = set().union(*(_producers_of(rel) for rel in UNDECLARED_READS))
    exposed = 0
    for source in ALL_STAGES:
        if UNWITNESSED not in adg._blanket_invalidate(source):
            continue
        kept = adg.transitive_invalidate(source)
        assert UNWITNESSED in kept, f"{source} dropped a stage with unwitnessed edges"
        exposed += bool(producers & (set(kept) | {source}))
    assert exposed >= 8, "the measured hazard shrank — re-measure before relaxing anything"


def test_an_empty_consumer_list_alone_does_not_make_a_stage_droppable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty means unknown. Only the explicit marker may mean none."""
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", ALL_GROUPS)
    real = load_contract(UNWITNESSED)
    assert real is not None
    _patch_contract(monkeypatch, UNWITNESSED, dataclasses.replace(real, consumers=[], propagation=[]))

    assert adg.declared_downstream(UNWITNESSED) == ()
    assert not adg.declared_terminal(UNWITNESSED)
    assert not adg.contract_edges_complete(UNWITNESSED)
    assert not adg.precision_droppable(UNWITNESSED)


# ---------------------------------------------------------------------------
# (b) The explicit terminal marker — the only spelling of "genuinely none"
# ---------------------------------------------------------------------------

def test_an_explicitly_terminal_stage_is_droppable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same empty consumer list as above, plus the affirmative declaration."""
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", ALL_GROUPS)
    real = load_contract(UNWITNESSED)
    assert real is not None
    marked = dataclasses.replace(
        real,
        consumers=[],
        propagation=[],
        raw=dict(real.raw, edges={"consumers": "terminal", "inputs": "complete"}),
    )
    _patch_contract(monkeypatch, UNWITNESSED, marked)

    assert adg.declared_terminal(UNWITNESSED)
    assert adg.contract_edges_complete(UNWITNESSED)
    assert adg.precision_droppable(UNWITNESSED)
    # ... and it really does leave an invalidation set it was being kept in.
    assert UNWITNESSED in adg._blanket_invalidate("content_context")
    assert UNWITNESSED not in adg.transitive_invalidate("content_context")


def test_the_terminal_marker_is_needed_for_both_directions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`consumers: terminal` answers the outbound half only; inbound still has to be witnessed."""
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", ALL_GROUPS)
    real = load_contract(UNWITNESSED)
    assert real is not None
    outbound_only = dataclasses.replace(
        real,
        consumers=[],
        propagation=[],
        raw=dict(real.raw, edges={"consumers": "terminal"}),
    )
    _patch_contract(monkeypatch, UNWITNESSED, outbound_only)
    assert adg.declared_terminal(UNWITNESSED)
    assert not adg.contract_edges_complete(UNWITNESSED)
    assert not adg.precision_droppable(UNWITNESSED)


def test_no_shipped_contract_claims_terminal_while_something_declares_a_consumer() -> None:
    """A marker contradicted by the graph is a wrong declaration, not a green light."""
    for sid in ALL_STAGES:
        if adg.declared_terminal(sid):
            assert not adg.declared_downstream(sid), f"{sid} claims terminal but has consumers"


# ---------------------------------------------------------------------------
# (c) The master path is never droppable, whatever the declarations say
# ---------------------------------------------------------------------------

def test_nothing_on_the_master_path_is_ever_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", ALL_GROUPS)
    master_path = [
        sid
        for sid in ALL_STAGES
        if adg.audio_touching(sid) or sid in MASTER_PATH_STAGES or adg.on_master_path(sid)
    ]
    assert set(MASTER_PATH_STAGES) <= set(master_path)
    for sid in master_path:
        assert adg.on_master_path(sid), sid
        assert not adg.precision_droppable(sid), sid
    for source in ALL_STAGES:
        blanket = set(adg._blanket_invalidate(source))
        kept = set(adg.transitive_invalidate(source))
        for sid in master_path:
            if sid in blanket:
                assert sid in kept, f"{source} dropped master-path stage {sid}"


def test_an_audio_stage_stays_even_when_its_contract_says_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Declarations cannot buy an audio stage out of the invalidation set."""
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", ALL_GROUPS)
    audio = sorted(s for s in AUDIO_MUTATING if s in ALL_STAGES and load_contract(s))
    assert audio, "fixture assumes audio-mutating pipeline stages exist"
    marked = {
        sid: dataclasses.replace(
            load_contract(sid),
            raw=dict(load_contract(sid).raw, edges={"consumers": "terminal", "inputs": "complete"}),
        )
        for sid in audio
    }
    real = load_contract
    monkeypatch.setattr(
        "interview_mux.artifact_dependency_graph.load_contract",
        lambda sid: marked.get(sid) or real(sid),
    )
    adg.build_graph.cache_clear()
    for sid in audio:
        assert adg.contract_edges_complete(sid), sid
        assert adg.on_master_path(sid), sid
        assert not adg.precision_droppable(sid), sid


# ---------------------------------------------------------------------------
# (d) The clamp holds through all of it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "strict",
    ["prepare", "prepare,understand-a,understand-b", ALL_GROUPS],
)
def test_the_precise_set_stays_a_subsequence_of_the_blanket_set(
    monkeypatch: pytest.MonkeyPatch, strict: str
) -> None:
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", strict)
    for sid in ALL_STAGES:
        blanket = adg._blanket_invalidate(sid)
        precise = adg.transitive_invalidate(sid)
        assert set(precise) <= set(blanket), f"{sid} invalidates MORE than the blanket set"
        assert precise == [s for s in blanket if s in set(precise)], f"{sid} reordered"


def test_the_subsequence_clamp_survives_a_terminal_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The marker may only subtract — it must never add or reorder either."""
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", ALL_GROUPS)
    real = load_contract(UNWITNESSED)
    assert real is not None
    _patch_contract(
        monkeypatch,
        UNWITNESSED,
        dataclasses.replace(
            real,
            consumers=[],
            propagation=[],
            raw=dict(real.raw, edges={"consumers": "terminal", "inputs": "complete"}),
        ),
    )
    for sid in ALL_STAGES:
        blanket = adg._blanket_invalidate(sid)
        precise = adg.transitive_invalidate(sid)
        assert precise == [s for s in blanket if s in set(precise)], sid


def test_the_precondition_only_ever_keeps_more(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-safe by construction: switching the precondition off may only drop MORE.

    The comparison is against the same code path with `contract_edges_complete`
    and `on_master_path` stubbed out — i.e. the §5.4 behaviour this task hardened.
    """
    monkeypatch.setenv("MUX_CONTRACT_STRICT_GROUPS", ALL_GROUPS)
    hardened = {sid: set(adg.transitive_invalidate(sid)) for sid in ALL_STAGES}

    monkeypatch.setattr(adg, "contract_edges_complete", lambda _sid: True)
    monkeypatch.setattr(adg, "on_master_path", lambda _sid: False)
    adg.build_graph.cache_clear()
    before = {sid: set(adg.transitive_invalidate(sid)) for sid in ALL_STAGES}

    assert any(before[sid] < hardened[sid] for sid in ALL_STAGES), "precondition changed nothing"
    for sid in ALL_STAGES:
        assert before[sid] <= hardened[sid], f"{sid} keeps FEWER stages after the precondition"
