"""Every contract `output` has an ownership ALLOW row (plan §4.2, `p1-ownership-xcheck`).

`write_permitted()` guards each `ctx` use behind `if ctx is not None`, so it runs
statically with `ctx=None` — no run dir needed. That makes "this stage declares
an artifact it has no authority to write" a **commit-time** failure instead of a
runtime `authority_denied:persist:<path>`, which is the single fingerprint behind
interventions i12–i54 of `exec_11871`.

`fail_closed()` is forced ON here: with it off, an output missing from the
catalog returns `unknown_path_warn` and the check passes silently.

The only tolerated gaps are `KNOWN_UNOWNED_CONTRACT_OUTPUTS`, imported from
`tests/test_path_ssot_drift.py` so there is exactly one pinned list. It may only
SHRINK — a new violation must be fixed with an `artifact_ownership.py` row, not
by widening the pin.
"""

from __future__ import annotations

import pytest

from interview_mux import artifact_ownership as ownership
from interview_mux.artifact_dependency_graph import build_graph
from interview_mux.stage_contract import (
    PIPELINE_TIERS,
    all_contract_stage_ids,
    contracts_dir,
    is_path_spec,
    load_contract,
)

from test_path_ssot_drift import KNOWN_UNOWNED_CONTRACT_OUTPUTS

# Non-stage (`gate` / `meta`) contracts whose outputs have no catalog row. These
# are NOT pipeline stages, so none of them can produce a runtime
# `authority_denied` on the dispatch path, and they are deliberately kept out of
# `KNOWN_UNOWNED_CONTRACT_OUTPUTS` (which is the pipeline-stage list and may only
# shrink). Each needs a decision from the owner of `artifact_ownership.py`:
#
#   optimal_questions  — `retired: true`; the contract keeps its historical
#                        output. Either drop the output or add a retired row.
#   sfx_brief          — declares `REMOVED_flow2/sfx_brief.json`, i.e. a path
#                        under the dead FLOW2 branch of plan §8.11. Should go
#                        away with the dead flow, not gain a row.
#   podcast_sfx_brief  — live `meta` brief writing `master/podcast_sfx_brief.json`
#                        with no catalog row. This one probably wants a real
#                        ALLOW row.
#
# Like the list above, this may only SHRINK.
KNOWN_UNOWNED_NON_STAGE_OUTPUTS: frozenset[tuple[str, str]] = frozenset(
    {
        ("optimal_questions", "understanding/gap_report.json"),
        ("sfx_brief", "REMOVED_flow2/sfx_brief.json"),
        ("podcast_sfx_brief", "master/podcast_sfx_brief.json"),
    }
)

ALL_KNOWN_UNOWNED = frozenset(KNOWN_UNOWNED_CONTRACT_OUTPUTS) | KNOWN_UNOWNED_NON_STAGE_OUTPUTS

# Declared output *families* — a directory or glob covering per-item writes. The
# ownership catalog is keyed on concrete paths (with glob support), and none of
# these families has a row yet, so `write_permitted` answers `unknown_path`.
# Reported, not asserted; each wants a glob row from the owner of
# `artifact_ownership.py`.
#
# The list shrinks as rows land. It grows only when contract population declares
# a family that was previously undeclared — which is the point: an undeclared
# per-item write is invisible, a declared one is a visible missing row. The
# `mastering/*` entries arrived that way with `understand-c`.
KNOWN_UNOWNED_OUTPUT_FAMILIES: frozenset[tuple[str, str]] = frozenset(
    {
        ("edl", "master/transitions/"),
        ("mastering_research_waves", "mastering/research/"),
        ("mmaudio_sfx", "master/sfx/"),
        ("mmaudio_sfx", "sound_design/assets/"),
        ("sound_design_vo_finalize", "vo_pickup/"),
        ("source_topology_build", "glob:understanding/speaker_samples/*.wav"),
        ("transcript_review_build", "glob:transcript/review_clips/*.wav"),
        ("vo_ingest", "vo_pickup/"),
        ("vo_synthesize", "master/transitions/"),
        ("vo_synthesize", "vo_pickup/synthesized/"),
    }
)


@pytest.fixture(autouse=True)
def _fail_closed_and_fresh_graph(monkeypatch: pytest.MonkeyPatch):
    """Assert with the catalog fail-closed, and never off a stale contract cache."""
    monkeypatch.setenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", "1")
    build_graph.cache_clear()
    yield
    build_graph.cache_clear()


def _all_contract_files() -> list[str]:
    """Includes `_`-prefixed contracts, which `all_contract_stage_ids()` skips."""
    return sorted(
        p.stem for p in contracts_dir().glob("*.yaml") if p.stem != "_contract-schema"
    )


def _violations(stage_ids: list[str]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for sid in stage_ids:
        contract = load_contract(sid)
        if not contract:
            continue
        for dep in contract.outputs:
            if not dep.path or is_path_spec(dep.path):
                continue
            ok, _reason = ownership.write_permitted(None, dep.path, sid)
            if not ok:
                out.add((sid, dep.path))
    return out


def _output_families() -> set[tuple[str, str]]:
    """Declared output families (`glob:` / directory) with no catalog row.

    These are real per-item writes — review clips, speaker samples, SFX assets,
    rendered transition WAVs — declared as a family because that is how
    `web/stages.py::StageInfo.artifacts` names them and how `flush_stage_writes`
    promotes them. `write_permitted` cannot answer for a spec, so they are
    reported rather than asserted, and each wants a glob catalog row from the
    owner of `artifact_ownership.py`.
    """
    out: set[tuple[str, str]] = set()
    for sid in _all_contract_files():
        contract = load_contract(sid)
        if not contract:
            continue
        for dep in contract.outputs:
            if not dep.path or not is_path_spec(dep.path):
                continue
            # A family whose spec *is* a catalog glob row (`mastering/research/
            # *.json`) is owned — `row_for_path` glob-matches it. Only families
            # the catalog cannot resolve at all belong on the gap list.
            if ownership.row_for_path(dep.path.removeprefix("glob:")) is not None:
                continue
            out.add((sid, dep.path))
    return out


def test_fail_closed_is_actually_on():
    assert ownership.fail_closed() is True, (
        "the x-check is meaningless with fail_closed off — unknown paths would pass"
    )


def test_every_pipeline_stage_output_has_an_allow_row():
    violations = _violations(
        [
            sid
            for sid in all_contract_stage_ids()
            if (c := load_contract(sid)) and c.tier in PIPELINE_TIERS
        ]
    )
    new = violations - set(KNOWN_UNOWNED_CONTRACT_OUTPUTS)
    assert new == set(), (
        "contract outputs declared without an ownership ALLOW row. Add the row in "
        "artifact_ownership.py — do NOT widen KNOWN_UNOWNED_CONTRACT_OUTPUTS: "
        f"{sorted(new)}"
    )


def test_every_contract_output_has_an_allow_row_including_non_stages():
    """Gate / meta contracts declare outputs too, and they are written for real."""
    violations = _violations(_all_contract_files())
    new = violations - ALL_KNOWN_UNOWNED
    assert new == set(), f"non-stage contract outputs without an ownership row: {sorted(new)}"


def test_no_pipeline_stage_hides_behind_the_non_stage_pin():
    """The non-stage pin must never cover a dispatchable stage."""
    from interview_mux.stage_contract import load_contract as _load

    leaked = {
        (sid, path)
        for sid, path in KNOWN_UNOWNED_NON_STAGE_OUTPUTS
        if (c := _load(sid)) and c.tier in PIPELINE_TIERS
    }
    assert leaked == set(), f"pipeline stages pinned as non-stage gaps: {sorted(leaked)}"


def test_pinned_gap_lists_only_shrink():
    """Every pinned entry is still a real violation — a stale pin hides a fixed row."""
    live = _violations(_all_contract_files())
    stale = ALL_KNOWN_UNOWNED - live
    assert stale == set(), (
        "these are now owned; remove them from the pinned gap lists: "
        f"{sorted(stale)}"
    )


def test_output_families_needing_a_glob_catalog_row_are_pinned():
    """Pinned so the list is visible and can only shrink as rows are added."""
    assert _output_families() == KNOWN_UNOWNED_OUTPUT_FAMILIES, (
        "declared output families changed — a glob row in artifact_ownership.py "
        "is the fix, not widening this list"
    )


def test_declared_producer_is_a_permitted_writer_of_the_input_path():
    """A `requires` edge is only real if the named producer may write that path.

    Catches the inverse of the i12–i54 class: a contract input pinned to a
    producer that has no authority over the artifact, which would route a heal
    to a stage that can only be denied.
    """
    bad: list[str] = []
    for sid in all_contract_stage_ids():
        contract = load_contract(sid)
        if not contract:
            continue
        for dep in contract.inputs:
            if not dep.producer or not dep.path:
                continue
            if dep.producer not in set(all_contract_stage_ids()):
                continue  # covered by test_contract_conformance
            ok, reason = ownership.write_permitted(None, dep.path, dep.producer)
            if not ok:
                bad.append(f"{sid}.inputs[{dep.path}] producer={dep.producer} ({reason})")
    allowed: set[str] = set()
    assert sorted(set(bad) - allowed) == [], (
        f"contract inputs pinned to a producer with no write authority: {sorted(set(bad))}"
    )
