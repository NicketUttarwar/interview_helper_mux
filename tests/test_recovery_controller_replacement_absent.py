"""H-02 is not ready: the contract system does not replace the recovery playbooks.

H-02 proposed deleting
`recovery_controller.py` (1,816L), justified for one of its 37 error classes by plan §2.3:
"solver admissibility makes `seed order` unreachable by construction". The rest of the row
already says the other 35 have no replacement.

[delivery-invariants-anomaly.md](../docs/cross-cutting/delivery-invariants-anomaly.md) §6
recorded that the §2.3 claim should be marked *not yet true* until `dispatch_stage` stops
raising the seed-order error. It still raises it, and these tests pin that end to end
rather than by citation: the guard fires on the first stage a fresh 0.1.0 run dispatches,
the solver has no authority to have prevented it, and `recovery_controller` is what turns
it into a resume stage.

The second candidate replacement is the contract `remediation` block, which
`stage_resilience.evaluate_stage_resilience` really does read. It cannot stand in either:
all 91 contracts declare the identical two coarse strategies, so it carries no information
about which of 37 error classes occurred and names no resume stage.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, isolated_run_ctx

CONTRACTS = Path("docs/cross-cutting/stage-contracts")
SEED_ORDER_STAGE = "transcript_review_build"


@pytest.fixture()
def fresh_brain_ctx(tmp_path: Path) -> RunContext:
    """A brand-new run on the 0.1.0 brain — nothing done, dispatch ledger armed."""
    ctx = isolated_run_ctx(tmp_path, "exec_recovery_replacement")
    init_run_meta_for_test(ctx)
    meta = ctx.read_json("run_meta.json")
    meta.update(
        {
            "homunculus_version": "0.1.0",
            "homunculus_control_plane": "deterministic",
            "run_mode": "full-auto",
            "full_auto": True,
        }
    )
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    return ctx


def test_the_seed_order_guard_is_reachable_on_the_first_dispatch(
    fresh_brain_ctx: RunContext,
) -> None:
    """"Unreachable by construction" is false — seed law still raises on the walk.

    `homunculus/runtime.dispatch_stage` raises on a non-empty `_seed_prereq_block`, so the
    block returned here *is* the RuntimeError the run sees. Stage order is seed-only.
    """
    from interview_mux.homunculus.runtime import _seed_prereq_block

    assert _seed_prereq_block(fresh_brain_ctx, SEED_ORDER_STAGE) == "audio_preclean"

    source = Path("src/interview_mux/homunculus/runtime.py").read_text(encoding="utf-8")
    assert 'f"seed order: complete {blocked} before running {stage}"' in source


def test_recovery_controller_is_the_only_thing_that_clears_that_block(
    fresh_brain_ctx: RunContext,
) -> None:
    """Classify, run one playbook, return the resume stage. Nothing else does this.

    This is the chain delivery-invariants-anomaly.md §3.1 traced from `pipeline.py`'s
    `except Exception` seam. Deleting the module removes the classification *and* the
    resume decision, and the seed-order RuntimeError propagates to the operator on the
    first stage of every 0.1.0 run.
    """
    from interview_mux.recovery_controller import (
        classify_error_class,
        handle_stage_failure,
        has_classified_playbook,
    )

    exc = RuntimeError(
        f"seed order: complete audio_preclean before running {SEED_ORDER_STAGE}"
    )
    error_class = classify_error_class(SEED_ORDER_STAGE, exc)
    assert error_class == "seed_order_prereq"
    assert has_classified_playbook(error_class) is True

    result = handle_stage_failure(fresh_brain_ctx, SEED_ORDER_STAGE, exc)
    assert result.status == "recovered"
    assert result.playbook_id == "seed_order_prereq"
    assert result.resume_stage == "audio_preclean"


def test_the_pipeline_recovery_seam_has_no_contract_alternative() -> None:
    """One import, in the one `except` branch that decides whether a failure is fatal."""
    source = Path("src/interview_mux/pipeline.py").read_text(encoding="utf-8")
    assert "from interview_mux.recovery_controller import handle_stage_failure" in source
    assert "handle_stage_failure(ctx, stage, exc)" in source


def test_contract_remediation_cannot_distinguish_the_37_error_classes() -> None:
    """The one non-inert contract remediation field is uniform across the whole pipeline.

    `stage_resilience.evaluate_stage_resilience` merges `contract.remediation` into a
    strategy ladder, so this field is genuinely read at runtime — which is why it is worth
    ruling out explicitly rather than by "contracts are inert". Every contract declares the
    same two verbs, so the ladder is identical for all 91 stages and for all 37 error
    classes. A playbook decides *which stage to resume from*; a strategy verb cannot.
    """
    from interview_mux.recovery_controller import CLASSIFIED_PLAYBOOKS

    declared: set[tuple[str, ...]] = set()
    contracts = 0
    for path in sorted(CONTRACTS.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "stage_id" not in raw:
            continue
        contracts += 1
        declared.add(tuple((raw.get("remediation") or {}).get("strategies") or []))

    assert contracts == 91
    assert declared <= {
        ("volley_retry", "full_stage_rerun"),
        ("full_stage_rerun",),
        ("volley_retry",),
        (),
    }
    assert any(t == ("volley_retry", "full_stage_rerun") for t in declared)
    assert len(CLASSIFIED_PLAYBOOKS) == 37
    assert not CLASSIFIED_PLAYBOOKS & {"volley_retry", "full_stage_rerun"}


def test_recovery_controller_has_live_importers_across_src_and_tools() -> None:
    """A module with this many production importers is not a dead control layer.

    Guards the "~7 callers" figure the subtraction audit carried. The real count is higher,
    and two of the importers are the run's only failure seams (`pipeline.py`,
    `homunculus/runtime.py`).
    """
    roots = (Path("src/interview_mux"), Path("tools"))
    importers = {
        path
        for root in roots
        for path in root.rglob("*.py")
        if path.name != "recovery_controller.py"
        and "from interview_mux.recovery_controller import"
        in path.read_text(encoding="utf-8")
    }
    names = {path.name for path in importers}
    assert {
        "pipeline.py",
        "runtime.py",
        "execution_contract.py",
        "operator_gates.py",
        "remediation_framework.py",
        "stage_input_checks.py",
        "full_auto_driver.py",
    } <= names
    assert len(importers) >= 7
