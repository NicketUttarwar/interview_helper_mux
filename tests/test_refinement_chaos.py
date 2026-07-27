"""Chaos tape fixtures — assert L0 classes and CFI caps for synthetic shapes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.refinement_catalog import ELIGIBLE_CLASS_VOCAB, is_whitelisted
from interview_mux.refinement_identity import (
    assert_acyclic_refines,
    assert_unique_registry,
    cfi_for_pass,
    register_builtin_cfis,
)
from interview_mux.refinement_ledger import can_run_refinement, record_call, save_ledger
from interview_mux.refinement_policy import POLICY_PACKS, resolve_policy_pack
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "refinement_chaos"


def _raw_json(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_topology(ctx: RunContext, topology_class: str, duration_sec: float, high_gaps: int = 0) -> None:
    _raw_json(
        ctx,
        "understanding/source_topology.json",
        {"topology_class": topology_class, "class": topology_class},
    )
    _raw_json(
        ctx,
        "understanding/source_acoustic_profile.json",
        {"duration_sec": duration_sec},
    )
    evals = []
    for i in range(high_gaps):
        evals.append(
            {
                "severity": "high",
                "gap_type": "definition_jargon" if i == 0 else "preface",
            }
        )
    _raw_json(ctx, "understanding/gap_evaluations.json", {"evaluations": evals})


@pytest.fixture()
def ctx(tmp_path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("exec_refinement_chaos", create=True)


@pytest.mark.parametrize(
    "fixture_name,expected_pack",
    [
        ("short_clean", "short_clean"),
        ("asymmetric_technical", "asymmetric_technical"),
        ("panel_multi_guest", "panel_multi_guest"),
        ("long_meander", "long_meander"),
    ],
)
def test_chaos_tape_pack_and_classes(ctx: RunContext, fixture_name: str, expected_pack: str) -> None:
    meta = json.loads((FIXTURES / f"{fixture_name}.json").read_text())
    _write_topology(ctx, meta["topology_class"], meta["duration_sec"], meta.get("high_gaps", 0))
    pack = resolve_policy_pack(ctx)
    assert pack["pack_id"] == expected_pack
    for c in pack["eligible_class_defaults"]:
        assert c in ELIGIBLE_CLASS_VOCAB
    if expected_pack == "short_clean":
        assert pack.get("simple_tape_override") is True
        assert pack["eligible_class_defaults"] == []
    else:
        assert pack["eligible_class_defaults"]
    assert expected_pack in POLICY_PACKS


def test_cfi_unique_and_second_run_blocked(ctx: RunContext) -> None:
    register_builtin_cfis()
    assert_unique_registry()
    assert_acyclic_refines()
    cfi = cfi_for_pass("gap_framing_recompose")
    assert cfi is not None
    save_ledger(
        ctx,
        {
            "run_id": ctx.run_id,
            "schema_version": 1,
            "calls": [],
            "counts_by_cfi": {},
            "order_of_refinement_pass_ids": [],
        },
    )
    assert can_run_refinement(ctx, cfi.cfi_id)
    record_call(
        ctx,
        cfi_id=cfi.cfi_id,
        human_key=cfi.human_key,
        stage_id="gap_framing_recompose",
        pass_id="gap_framing_recompose",
        pass_index=2,
        kind="refinement",
        outcome="ok",
    )
    assert not can_run_refinement(ctx, cfi.cfi_id)
    assert is_whitelisted("gap_framing_recompose")
