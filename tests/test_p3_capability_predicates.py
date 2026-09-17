"""p3-capability-predicates — rails and control flow are two questions, not one.

``is_homunculus_run`` used to answer both "should I write a ledger row?" and "is an
LLM picking the next stage?" at ~22 call sites. 0.2.0 is the counter-example that
makes the conflation wrong: it keeps every rail while the deterministic walk picks
stages. The invariant a future ``kind="solver"`` brain would otherwise break is
that the rails predicate is keyed on the capability, not on the brain's ``kind``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus import version as brain_version
from interview_mux.homunculus.runtime import (
    conductor_owns_control_flow,
    has_dispatch_ledger,
    has_homunculus_features,
    is_homunculus_run,
    recovery_allowed,
)
from run_fixtures import isolated_run_ctx


def _run(tmp_path: Path, name: str, version: str) -> object:
    ctx = isolated_run_ctx(tmp_path, name)
    brain = brain_version.resolve_brain(version)
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": version,
            "homunculus_kind": brain.kind,
            "homunculus_control_plane": brain.control_plane,
        },
        skip_handoff=True,
    )
    return ctx


def test_020_rails_on_control_flow_deterministic(tmp_path: Path) -> None:
    ctx = _run(tmp_path, "p3_020", "0.2.0")
    assert has_dispatch_ledger(ctx) is True
    assert has_homunculus_features(ctx) is True
    assert conductor_owns_control_flow(ctx) is False


def test_010_rails_on_control_flow_llm(tmp_path: Path) -> None:
    ctx = _run(tmp_path, "p3_010", "0.1.0")
    assert has_dispatch_ledger(ctx) is True
    assert has_homunculus_features(ctx) is True
    assert conductor_owns_control_flow(ctx) is True


def test_000_has_neither_rails_nor_llm_control_flow(tmp_path: Path) -> None:
    ctx = _run(tmp_path, "p3_000", "0.0.0")
    assert has_dispatch_ledger(ctx) is False
    assert has_homunculus_features(ctx) is False
    assert conductor_owns_control_flow(ctx) is False
    assert is_homunculus_run(ctx) is False


def test_rails_survive_a_new_kind_that_is_not_homunculus(monkeypatch) -> None:
    """A ``kind="solver"`` brain keeps the rails; only the original walk has none.

    This is the exact regression that forced 0.2.0 to stay ``kind=homunculus``:
    with rails keyed on ``kind == "homunculus"``, registering a new kind dropped
    the ledger, admit and dispatch budget at every call site at once.
    """
    solver = brain_version.HomunculusBrain(
        id="0.3.0",
        label="Solver",
        summary="admissibility solver",
        kind="solver",
        control_plane="deterministic",
    )
    brains = brain_version.list_brains() + (solver,)
    monkeypatch.setattr(brain_version, "list_brains", lambda: brains)

    assert brain_version.is_homunculus_brain("0.3.0") is False
    assert brain_version.brain_has_dispatch_ledger("0.3.0") is True
    assert brain_version.brain_has_homunculus_features("0.3.0") is True
    assert brain_version.llm_owns_control_flow("0.3.0") is False
    assert brain_version.brain_has_dispatch_ledger("0.0.0") is False


def test_unknown_version_has_no_capabilities() -> None:
    assert brain_version.brain_has_dispatch_ledger("9.9.9") is False
    assert brain_version.brain_has_homunculus_features("9.9.9") is False
    assert brain_version.llm_owns_control_flow("9.9.9") is False


def test_recovery_is_not_deferred_to_an_analysis_that_cannot_arrive(
    tmp_path: Path,
) -> None:
    """Only the conductor loop can produce ``analyze_issue`` output.

    Under 0.2.0 no conductor turn is ever spent, so gating recovery on the rails
    predicate stranded every novel failure waiting for analysis that never came.
    """
    ctx_020 = _run(tmp_path, "p3_recover_020", "0.2.0")
    assert recovery_allowed(ctx_020, "sonic_context_build") is True

    ctx_010 = _run(tmp_path, "p3_recover_010", "0.1.0")
    assert recovery_allowed(ctx_010, "sonic_context_build") is False


def test_snapshot_status_reports_rails_and_control_flow_apart(tmp_path: Path) -> None:
    from interview_mux.homunculus.runtime import snapshot_status

    ctx = _run(tmp_path, "p3_snapshot", "0.2.0")
    snap = snapshot_status(ctx)
    assert snap["active"] is True
    assert snap["conductor_owns_control_flow"] is False


@pytest.mark.parametrize(
    "module_name, attr",
    [
        ("interview_mux.media_ip_cta", "enabled"),
        ("interview_mux.framing_posture", "should_run_framing_posture_llm"),
        ("interview_mux.publishability_boundary", "publishability_enforce"),
    ],
)
def test_feature_tier_sites_stay_on_under_020(
    tmp_path: Path, module_name: str, attr: str
) -> None:
    """Content features are a brain-tier question, not a control-flow question."""
    import importlib

    mod = importlib.import_module(module_name)
    ctx = _run(tmp_path, f"p3_feature_{attr}", "0.2.0")
    fn = getattr(mod, attr)
    # framing posture also consults config/eligibility — only assert it is not
    # refused for the brain reason, which is what this predicate governs.
    if attr == "should_run_framing_posture_llm":
        assert has_homunculus_features(ctx) is True
    else:
        assert fn(ctx) is True


def test_no_production_call_site_asks_the_ambiguous_question() -> None:
    """``is_homunculus_run`` survives as an identity alias with no callers left.

    Every production reference must live in the module that defines it; a new call
    site elsewhere is a site asking "is an LLM driving?" when it means something
    else, which is the bug this to-do removes.
    """
    from interview_mux.config import repo_root

    root = repo_root()
    offenders: list[str] = []
    for base in ("src", "tools"):
        for path in (root / base).rglob("*.py"):
            if path.name == "runtime.py" and path.parent.name == "homunculus":
                continue
            for num, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "is_homunculus_run" in line:
                    offenders.append(f"{path.relative_to(root)}:{num}: {line.strip()}")
    assert offenders == [], offenders
