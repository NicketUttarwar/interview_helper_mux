"""Source-level guards: Land Honesty wiring must not regress silently."""

from __future__ import annotations

import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src" / "interview_mux"


def test_done_authority_exports_land_honesty_apis() -> None:
    text = (_SRC / "done_authority.py").read_text(encoding="utf-8")
    for needle in (
        "def unpaid_land_reason",
        "def land_honest",
        "def unpaid_land_blocks_promote",
        "SHARED_PATH_PRODUCER_STAGES",
        "LAYUP_AUTHORITY_STAGES",
        "Land Honesty",
    ):
        assert needle in text, needle


def test_promote_orphan_calls_unpaid_land_blocks_promote() -> None:
    text = (_SRC / "delivery_guardrails.py").read_text(encoding="utf-8")
    assert "def promote_complete_orphan_stage_done" in text
    # Gate must sit inside promote, not only in comments.
    promote_idx = text.index("def promote_complete_orphan_stage_done")
    window = text[promote_idx : promote_idx + 2500]
    assert "unpaid_land_blocks_promote" in window


def test_mix_junction_remaster_clear_only_api() -> None:
    text = (_SRC / "mix_junction_seat.py").read_text(encoding="utf-8")
    assert "def begin_remaster" in text
    assert "def clear_remaster" in text
    assert "def speech_first_remaster_owed" in text
    assert "def ensure_speech_first_remaster" in text


def test_heal_or_raise_uses_seed_complete_not_bare_is_done() -> None:
    text = (_SRC / "stage_completion.py").read_text(encoding="utf-8")
    assert "def heal_or_raise" in text
    idx = text.index("def heal_or_raise")
    window = text[idx : idx + 1200]
    assert "seed_stage_complete" in window
    assert "Heal Success" in window or "seed-complete" in window


def test_pipeline_shared_analysis_uses_land_honest_or_seed() -> None:
    text = (_SRC / "pipeline.py").read_text(encoding="utf-8")
    assert "shared_analysis_chain_complete" in text
    idx = text.index("def shared_analysis_chain_complete")
    window = text[idx : idx + 2000]
    assert (
        "land_honest" in window
        or "seed_stage_complete" in window
        or "may_skip_as_complete" in window
        or "is_seed_complete" in window
    )


def test_census_documents_land_honesty() -> None:
    census = (
        _REPO
        / ".cursor"
        / "heal-clinic"
        / "classes"
        / "hollow_pass"
        / "done_constitution_census.md"
    )
    text = census.read_text(encoding="utf-8")
    assert "unpaid_land_reason" in text
    assert "land_honest" in text
