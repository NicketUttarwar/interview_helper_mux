"""Heal / force-mark honesty — gap + analysis paths (MUX_FORENSICS=0).

Hollow ``mark_done_raw`` + incomplete artifacts must not greenwash Finished:
``heal_or_raise`` raises and ``seed_stage_complete`` stays False. Shared analysis
chain and ``gap_compose_stage_done`` must use land-honest / seed, not bare is_done.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.done_authority import land_honest
from interview_mux.pipeline import shared_analysis_chain_complete
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_raise
from interview_mux.stages.gaps import (
    _heal_gap_framing_compose_if_complete,
    gap_compose_stage_done,
)
from run_fixtures import isolated_run_ctx, mark_done_raw

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src" / "interview_mux"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_land_honesty_heal_flap")


# --- Behavior: hollow stamp → heal_or_raise raises, seed stays False ---


@pytest.mark.parametrize(
    "sid,thin_rel,thin_doc",
    [
        (
            "missing_framing",
            "understanding/gap_evaluations.json",
            None,  # stamp-alone: missing primary
        ),
        (
            "gap_framing_compose",
            "understanding/gap_report.json",
            {"interviewer_lines": [], "nugget_layup_authority": True},
        ),
        (
            "nugget_corpus_mine",
            "understanding/nugget_corpus.json",
            {"nuggets": []},
        ),
    ],
)
def test_hollow_heal_or_raise_refuses_incomplete(
    ctx: RunContext,
    monkeypatch: pytest.MonkeyPatch,
    sid: str,
    thin_rel: str,
    thin_doc: dict | None,
) -> None:
    """mark_done_raw + incomplete primary → heal_or_raise raises; seed False."""
    if sid in ("gap_framing_compose", "nugget_corpus_mine"):
        monkeypatch.setattr(
            "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
        )
    if thin_doc is not None:
        ctx.write_json(thin_rel, thin_doc)
    mark_done_raw(ctx, sid)
    assert ctx.is_done(sid)

    with pytest.raises(RuntimeError):
        heal_or_raise(ctx, sid)

    assert seed_stage_complete(ctx, sid) is False
    assert land_honest(ctx, sid) is False


def test_heal_gap_compose_helper_raises_on_hollow(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_heal_gap_framing_compose_if_complete`` must not early-return on bare is_done."""
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )
    mark_done_raw(ctx, "gap_framing_compose")
    with pytest.raises(RuntimeError):
        _heal_gap_framing_compose_if_complete(ctx)
    assert seed_stage_complete(ctx, "gap_framing_compose") is False


def test_gap_compose_stage_done_rejects_hollow_stamp(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gap_compose_stage_done must use land_honest/seed — hollow stamp is not done."""
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    mark_done_raw(ctx, "gap_framing_compose", "optimal_questions")
    assert ctx.is_done("gap_framing_compose")
    assert gap_compose_stage_done(ctx) is False
    assert seed_stage_complete(ctx, "gap_framing_compose") is False


def test_episode_structure_hollow_stamp_blocks_shared_chain(ctx: RunContext) -> None:
    """Hollow episode_structure_compose stamp ⇒ shared_analysis_chain_complete False."""
    mark_done_raw(ctx, "episode_structure_compose")
    assert ctx.is_done("episode_structure_compose")
    with pytest.raises(RuntimeError):
        heal_or_raise(ctx, "episode_structure_compose")
    assert shared_analysis_chain_complete(ctx) is False
    assert land_honest(ctx, "episode_structure_compose") is False
    assert seed_stage_complete(ctx, "episode_structure_compose") is False


# --- Source guards: heal helpers + gap_compose must not regress to bare is_done ---


def test_gap_compose_stage_done_source_uses_land_honest() -> None:
    text = (_SRC / "stages" / "gaps.py").read_text(encoding="utf-8")
    assert "def gap_compose_stage_done" in text
    idx = text.index("def gap_compose_stage_done")
    window = text[idx : idx + 600]
    assert "land_honest" in window or "seed_stage_complete" in window
    assert "ctx.is_done(" not in window


def test_heal_gap_compose_helper_no_bare_is_done_early_return() -> None:
    text = (_SRC / "stages" / "gaps.py").read_text(encoding="utf-8")
    assert "def _heal_gap_framing_compose_if_complete" in text
    idx = text.index("def _heal_gap_framing_compose_if_complete")
    window = text[idx : idx + 500]
    assert "heal_or_raise" in window
    assert "if ctx.is_done" not in window
    assert "if not ctx.is_done" not in window


def test_heal_nugget_layup_helper_no_bare_is_done_early_return() -> None:
    text = (_SRC / "stages" / "analysis_extended.py").read_text(encoding="utf-8")
    assert "def _heal_nugget_layup_compose_if_complete" in text
    idx = text.index("def _heal_nugget_layup_compose_if_complete")
    window = text[idx : idx + 1200]
    assert "heal_or_raise" in window
    assert "if ctx.is_done" not in window
    assert "Land Honesty" in window or "never early-return" in window


def test_gaps_and_analysis_import_heal_apis() -> None:
    gaps = (_SRC / "stages" / "gaps.py").read_text(encoding="utf-8")
    analysis = (_SRC / "stages" / "analysis_extended.py").read_text(encoding="utf-8")
    assert "heal_or_raise" in gaps
    assert "heal_or_refuse_mark" in gaps
    assert "heal_or_refuse_mark" in analysis
    assert "heal_or_raise" in analysis
