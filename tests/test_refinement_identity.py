"""CFI identity registry — uniqueness and acyclic refines_cfi chains."""

from __future__ import annotations

import pytest

import interview_mux.refinement_catalog  # noqa: F401 — ensures builtin CFIs are registered
from interview_mux.refinement_identity import (
    CFI,
    all_cfis,
    assert_acyclic_refines,
    assert_unique_registry,
    cfi_for_pass,
    register_cfi,
)

REQUIRED_BUILTIN_PASS_IDS = {
    "gap_framing_compose",
    "gap_framing_recompose",
    "refinement_agenda",
    "narrative_arc_refine",
    "ranking_refine",
    "transitions_refine",
    "sdp_intent_refine",
    "edl_narrative_refine",
}


def test_all_required_builtin_cfis_are_registered() -> None:
    pass_ids = {c.pass_id for c in all_cfis()}
    assert REQUIRED_BUILTIN_PASS_IDS <= pass_ids


def test_cfi_id_is_twelve_char_hex_and_stable() -> None:
    cfi = CFI(
        module_path="interview_mux.tests",
        qualname="fake_fn",
        stage_id="fake_stage",
        pass_id="fake_pass",
        semantic_role="test",
        file_path="tests/fake_a.py",
    )
    same_identity_other_file = CFI(
        module_path="interview_mux.tests",
        qualname="fake_fn",
        stage_id="fake_stage",
        pass_id="fake_pass",
        semantic_role="test",
        file_path="tests/fake_b.py",
    )
    assert len(cfi.cfi_id) == 12
    int(cfi.cfi_id, 16)  # valid hex
    assert cfi.cfi_id == same_identity_other_file.cfi_id  # file_path isn't part of identity


def test_human_key_format() -> None:
    cfi = CFI(
        module_path="interview_mux.mod",
        qualname="fn",
        stage_id="stage_x",
        pass_id="pass_x",
        semantic_role="refine",
    )
    assert cfi.human_key == "interview_mux.mod::fn::stage_x::pass_x"


def test_gap_framing_recompose_refines_the_draft_cfi() -> None:
    draft = cfi_for_pass("gap_framing_compose")
    recompose = cfi_for_pass("gap_framing_recompose")
    assert draft is not None
    assert recompose is not None
    assert recompose.refines_cfi == draft.cfi_id


def test_assert_unique_registry_passes_for_builtins() -> None:
    assert_unique_registry()


def test_assert_acyclic_refines_passes_for_builtins() -> None:
    assert_acyclic_refines()


def test_register_cfi_raises_on_conflicting_human_key() -> None:
    """Same human_key (module/qualname/stage/pass) but different semantic_role -> different
    cfi_id but identical human_key — must be rejected as ambiguous."""
    first = CFI(
        module_path="interview_mux.tests",
        qualname="dup_fn",
        stage_id="dup_stage",
        pass_id="dup_pass",
        semantic_role="role_a",
    )
    register_cfi(first)
    conflicting = CFI(
        module_path="interview_mux.tests",
        qualname="dup_fn",
        stage_id="dup_stage",
        pass_id="dup_pass",
        semantic_role="role_b",
    )
    with pytest.raises(ValueError, match="human_key"):
        register_cfi(conflicting)


def test_register_cfi_is_idempotent_for_identical_entry() -> None:
    cfi = CFI(
        module_path="interview_mux.tests",
        qualname="idempotent_fn",
        stage_id="idempotent_stage",
        pass_id="idempotent_pass",
        semantic_role="role",
    )
    register_cfi(cfi)
    register_cfi(cfi)  # no raise
    assert cfi_for_pass("idempotent_pass") is not None


def test_assert_acyclic_refines_detects_cycle() -> None:
    cfi_b = CFI(
        module_path="interview_mux.tests",
        qualname="cyc_b",
        stage_id="cyc_stage",
        pass_id="cyc_b",
        semantic_role="x",
    )
    cfi_a = CFI(
        module_path="interview_mux.tests",
        qualname="cyc_a",
        stage_id="cyc_stage",
        pass_id="cyc_a",
        semantic_role="x",
        refines_cfi=cfi_b.cfi_id,
    )
    cfi_b_cyclic = CFI(
        module_path="interview_mux.tests",
        qualname="cyc_b",
        stage_id="cyc_stage",
        pass_id="cyc_b",
        semantic_role="x",
        refines_cfi=cfi_a.cfi_id,
    )
    with pytest.raises(AssertionError, match="Cyclic"):
        assert_acyclic_refines([cfi_a, cfi_b_cyclic])


def test_assert_acyclic_refines_accepts_valid_chain() -> None:
    root = CFI(
        module_path="interview_mux.tests",
        qualname="chain_root",
        stage_id="chain_stage",
        pass_id="chain_root",
        semantic_role="draft",
    )
    child = CFI(
        module_path="interview_mux.tests",
        qualname="chain_child",
        stage_id="chain_stage",
        pass_id="chain_child",
        semantic_role="refine",
        refines_cfi=root.cfi_id,
    )
    assert_acyclic_refines([root, child])  # no raise
