"""PIN_PREMATURE family matrix — Partial Zero DP-B1+B2+B3+B6 (all Option A).

One heal surface: ``producer_pin_for_token`` + sole ``incompleteness_resume_stage``.
High coverage for compound / substring / unknown-class / single-API laws.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from interview_mux.stage_completion import (
    incompleteness_resume_stage,
    premature_class_pin,
    producer_pin_for_token,
)
from run_fixtures import isolated_run_ctx

_VO_LANDINGS = frozenset(
    {"vo_synthesize", "vo_line_adjudicate", "nugget_layup_compose", "missing_framing"}
)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "pin_premature_family")


# --- B1: compound longest / most-specific ---------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "mix_unseated and premature_complete:vo_g1",
        "premature_complete:vo_g1 mix_unseated",
        "delivery:mix_unseated;premature_complete:vo_g1",
        "mix_outputs_seated premature_complete:vo_g1",
        "mix unseated + premature_complete:g1_incomplete",
        "authority_denied:mix_unseated premature_complete:vo_g1 identical",
    ],
)
def test_b1_compound_vo_beats_mix_family(ctx, token: str) -> None:
    pin = producer_pin_for_token(token, ctx=ctx)
    assert pin in _VO_LANDINGS, (token, pin)
    assert pin != "mix"


def test_b1_mix_unseated_alone_still_pins_mix(ctx) -> None:
    assert producer_pin_for_token("mix_unseated", ctx=ctx) == "mix"
    assert producer_pin_for_token("assembly mix_outputs_seated refused", ctx=ctx) == "mix"


def test_b1_mix_seat_compound_does_not_invent_fake_stage(ctx) -> None:
    """Compound mix_unseated + premature mix_seat stays on seating/music producers."""
    pin = producer_pin_for_token(
        "mix_unseated premature_complete:mix_seat", ctx=ctx
    )
    assert pin in {
        "mix",
        "junction_snip_qa",
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
    }
    assert "mix_seat" not in pin


# --- B2: exact token, not substring ---------------------------------------


@pytest.mark.parametrize(
    "prose",
    [
        "remix bed failed",
        "premix commitment diverge",
        "music remix render oom",
        "intermix layers",
        "failed: remix_palette",
    ],
)
def test_b2_prose_does_not_false_pin_mix(ctx, prose: str) -> None:
    pin = producer_pin_for_token(prose, ctx=ctx, default="")
    assert pin != "mix", prose


@pytest.mark.parametrize(
    "token,expect",
    [
        ("mix_unseated", "mix"),
        ("mix_outputs_seated", "mix"),
        ("artifact_missing:mix", "mix"),
        ("g1_vo_open", "vo_synthesize"),
        ("hosted_vo_floor_unmet", "nugget_layup_compose"),
    ],
)
def test_b2_exact_structured_tokens_still_pin(ctx, token: str, expect: str) -> None:
    assert producer_pin_for_token(token, ctx=ctx) == expect


# --- B3: unknown premature class ------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "delivery:premature_complete:brand_new_class",
        "premature_complete:totally_invented",
        "analysis:premature_complete:xyzzy_not_a_stage",
    ],
)
def test_b3_unknown_class_defaults_transitions_not_fake_stage(ctx, token: str) -> None:
    pin = producer_pin_for_token(token, ctx=ctx)
    assert pin == "transitions"
    assert pin != token.split(":")[-1]
    cls_pin = premature_class_pin(token, ctx)
    assert cls_pin == "transitions"


def test_b3_named_classes_never_fake_and_vo_not_transitions(ctx) -> None:
    pin = producer_pin_for_token("delivery:premature_complete:vo_g1", ctx=ctx)
    assert pin in _VO_LANDINGS
    assert pin != "transitions"

    pin_m = producer_pin_for_token("delivery:premature_complete:music_epoch", ctx=ctx)
    assert pin_m != "transitions"

    assert producer_pin_for_token("premature_complete", ctx=ctx) == "transitions"
    assert (
        producer_pin_for_token(
            "analysis:premature_complete:stage:gap_framing_compose", ctx=ctx
        )
        == "gap_framing_compose"
    )


# --- B6: single incompleteness_resume_stage API ---------------------------


def test_b6_single_definition_and_signature() -> None:
    import interview_mux.stage_completion as sc

    src = Path(sc.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    defs = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "incompleteness_resume_stage"
    ]
    assert len(defs) == 1, f"expected one def, found {len(defs)}"
    sig = inspect.signature(sc.incompleteness_resume_stage)
    params = list(sig.parameters)
    assert params == ["ctx", "consumer_stage"], params


def test_b6_callers_use_ctx_consumer_signature(ctx) -> None:
    # Smoke: structured API accepts consumer stage ids (no prose-first overload).
    out = incompleteness_resume_stage(ctx, "mix")
    assert out is None or isinstance(out, str)


# --- Family integration: thrash-shaped compounds --------------------------


@pytest.mark.parametrize(
    "token,must_not,must_be_in",
    [
        (
            "identical_failure mix_unseated premature_complete:vo_g1",
            {"mix", "transitions"},
            _VO_LANDINGS,
        ),
        (
            "heal_navigate: remix bed + premature_complete:vo_g1",
            {"mix"},
            _VO_LANDINGS,
        ),
        (
            "premature_complete:brand_new_class mix_unseated",
            {"brand_new_class"},
            {"transitions", "mix"},  # unknown→transitions beats or ties; mix alone ok if wins
        ),
    ],
)
def test_family_integration_compounds(
    ctx, token: str, must_not: set[str], must_be_in: set[str]
) -> None:
    pin = producer_pin_for_token(token, ctx=ctx, default="")
    for bad in must_not:
        assert pin != bad, (token, pin)
    if "brand_new_class" in token:
        # Unknown class → transitions; mix_unseated also scored — longest wins.
        # premature_complete:brand_new_class length > mix_unseated → transitions.
        assert pin == "transitions", pin
    else:
        assert pin in must_be_in, (token, pin)
