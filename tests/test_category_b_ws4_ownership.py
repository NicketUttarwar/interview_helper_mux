"""Category B WS4 ownership, remap, and freeze automation."""

from __future__ import annotations

from itertools import product

import pytest

from interview_mux import artifact_ownership as ownership
from interview_mux.segment_id_remap import SHARED_REMAP_RELS
from tools.ownership_new_stage_checklist import (
    remap_call_site_findings,
    shared_co_writer_findings,
)


EPOCHS = (
    "pre_soft_freeze",
    "soft_freeze",
    "hard_freeze",
    "edl_sealed",
    "mix_seated",
    "junction_committed",
)


@pytest.mark.parametrize(
    ("rel", "stage", "epoch"),
    product(SHARED_REMAP_RELS, ownership.SEGMENT_ID_REMAP_STAGES, EPOCHS),
)
def test_shared_remap_x_stages_matrix(
    monkeypatch: pytest.MonkeyPatch,
    rel: str,
    stage: str,
    epoch: str,
) -> None:
    class _Ctx:
        pass

    monkeypatch.setattr(ownership, "current_epoch", lambda _ctx: epoch)
    ok, reason = ownership.write_permitted(
        _Ctx(),
        rel,
        stage,
        mutation_class="segment_id_remap",
    )
    assert ok, (rel, stage, epoch, reason)


def test_shared_remap_requires_mutation_class(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Ctx:
        pass

    monkeypatch.setattr(ownership, "current_epoch", lambda _ctx: "hard_freeze")
    ok, reason = ownership.write_permitted(
        _Ctx(),
        SHARED_REMAP_RELS[0],
        ownership.SEGMENT_ID_REMAP_STAGES[0],
    )
    assert ok is False
    assert reason == "mutation_class_required:segment_id_remap"


def test_remap_call_sites_are_registered() -> None:
    assert remap_call_site_findings() == []


def test_shared_co_writer_literals_are_producers() -> None:
    assert shared_co_writer_findings() == []


@pytest.mark.parametrize(
    ("stage", "mutation", "allowed_epochs"),
    [
        (
            "edl_narrative_audit",
            "narrative_metadata_align",
            {"pre_soft_freeze", "soft_freeze", "hard_freeze"},
        ),
        (
            "edl_narrative_audit",
            "narrative_host_repair",
            {"pre_soft_freeze"},
        ),
        (
            "gap_framing_compose",
            "compose_copy",
            {"pre_soft_freeze", "soft_freeze"},
        ),
        (
            "transitions",
            "transition_dedupe",
            {"pre_soft_freeze", "soft_freeze", "hard_freeze"},
        ),
    ],
)
def test_freeze_write_policy(
    stage: str,
    mutation: str,
    allowed_epochs: set[str],
) -> None:
    for epoch in ("pre_soft_freeze", "soft_freeze", "hard_freeze"):
        assert ownership.freeze_write_allowed(
            None,
            stage,
            mutation,
            epoch=epoch,
        ) is (epoch in allowed_epochs)


def test_edl_narrative_audit_may_align_narrative_plan_under_hard_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MUX_FORENSICS=0: metadata align of narrative_plan under hard_freeze (exec_13167)."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    monkeypatch.setattr(ownership, "current_epoch", lambda _ctx: "hard_freeze")

    class _Ctx:
        pass

    ok, reason = ownership.write_permitted(
        _Ctx(),
        "master/narrative_plan.json",
        "edl_narrative_audit",
        role="producer",
        verb="persist",
        mutation_class="narrative_metadata_align",
    )
    assert ok is True, reason
    assert reason == "allow"
