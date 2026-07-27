"""Canonical Function Identity (CFI) for refinement passes — one row per function."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CFI:
    module_path: str
    qualname: str
    stage_id: str
    pass_id: str
    semantic_role: str
    file_path: str = ""
    refines_cfi: str | None = None

    @property
    def human_key(self) -> str:
        return f"{self.module_path}::{self.qualname}::{self.stage_id}::{self.pass_id}"

    @property
    def cfi_id(self) -> str:
        raw = "|".join(
            [
                self.module_path,
                self.qualname,
                self.stage_id,
                self.pass_id,
                self.semantic_role,
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


_REGISTRY: dict[str, CFI] = {}
_BY_HUMAN: dict[str, CFI] = {}


def register_cfi(cfi: CFI) -> CFI:
    existing = _REGISTRY.get(cfi.cfi_id)
    if existing is not None and existing != cfi:
        raise ValueError(f"Duplicate CFI id {cfi.cfi_id}: {existing.human_key} vs {cfi.human_key}")
    if cfi.human_key in _BY_HUMAN and _BY_HUMAN[cfi.human_key].cfi_id != cfi.cfi_id:
        raise ValueError(f"Duplicate CFI human_key {cfi.human_key}")
    _REGISTRY[cfi.cfi_id] = cfi
    _BY_HUMAN[cfi.human_key] = cfi
    return cfi


def all_cfis() -> list[CFI]:
    return list(_REGISTRY.values())


def get_cfi(cfi_id: str) -> CFI | None:
    return _REGISTRY.get(cfi_id)


def get_cfi_by_human_key(human_key: str) -> CFI | None:
    return _BY_HUMAN.get(human_key)


def cfi_for_pass(pass_id: str) -> CFI | None:
    for cfi in _REGISTRY.values():
        if cfi.pass_id == pass_id or (pass_id and cfi.stage_id == pass_id and cfi.pass_id == pass_id):
            return cfi
    return None


def assert_unique_registry() -> None:
    ids = [c.cfi_id for c in _REGISTRY.values()]
    keys = [c.human_key for c in _REGISTRY.values()]
    if len(ids) != len(set(ids)):
        raise AssertionError("CFI registry has duplicate cfi_id values")
    if len(keys) != len(set(keys)):
        raise AssertionError("CFI registry has duplicate human_key values")


def assert_acyclic_refines(cfis: Iterable[CFI] | None = None) -> None:
    items = list(cfis) if cfis is not None else all_cfis()
    by_id = {c.cfi_id: c for c in items}

    def visit(cid: str, stack: set[str]) -> None:
        if cid in stack:
            raise AssertionError(f"Cyclic refines_cfi involving {cid}")
        cfi = by_id.get(cid)
        if cfi is None or not cfi.refines_cfi:
            return
        stack.add(cid)
        visit(cfi.refines_cfi, stack)
        stack.remove(cid)

    for cfi in items:
        visit(cfi.cfi_id, set())


def register_builtin_cfis() -> None:
    """Idempotent registration of catalog CFIs."""
    if _REGISTRY:
        return
    draft = register_cfi(
        CFI(
            module_path="interview_mux.gap_framing",
            qualname="persist_gap_framing_companion_artifacts",
            stage_id="gap_framing_compose",
            pass_id="gap_framing_compose",
            semantic_role="draft",
            file_path="src/interview_mux/gap_framing.py",
        )
    )
    register_cfi(
        CFI(
            module_path="interview_mux.refinement_passes",
            qualname="run_gap_framing_recompose",
            stage_id="gap_framing_recompose",
            pass_id="gap_framing_recompose",
            semantic_role="refinement",
            file_path="src/interview_mux/refinement_passes.py",
            refines_cfi=draft.cfi_id,
        )
    )
    register_cfi(
        CFI(
            module_path="interview_mux.refinement_agenda",
            qualname="run_refinement_agenda",
            stage_id="refinement_agenda",
            pass_id="refinement_agenda",
            semantic_role="agenda",
            file_path="src/interview_mux/refinement_agenda.py",
        )
    )
    for stage, role in (
        ("narrative_arc_refine", "refine"),
        ("ranking_refine", "refine"),
        ("transitions_refine", "refine"),
        ("sdp_intent_refine", "refine"),
        ("edl_narrative_refine", "refine"),
        ("selection_framing_apply", "apply"),
    ):
        register_cfi(
            CFI(
                module_path="interview_mux.refinement_passes",
                qualname=f"run_{stage}",
                stage_id=stage,
                pass_id=stage,
                semantic_role=role,
                file_path="src/interview_mux/refinement_passes.py",
            )
        )
    assert_unique_registry()
    assert_acyclic_refines()


register_builtin_cfis()
