"""R2: gap_report scaffolding uses live hard codes; required lines refuse-not-rewrite (S2)."""

from __future__ import annotations

import pytest

from interview_mux.artifact_sanitize.gap_report import (
    _scaffolding_codes,
    _strip_scaffolding,
    sanitize_gap_report,
)
from interview_mux.spoken_meta_lint import (
    is_hard_structure_violation,
    spoken_structure_hits,
)
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "r2_scaffold")


def test_strip_scaffolding_catches_spoken_show_scaffold() -> None:
    text = "Welcome back — in today's episode we unpack the trial design."
    assert "spoken_show_scaffold" in spoken_structure_hits(text)
    assert is_hard_structure_violation("spoken_show_scaffold")
    assert "spoken_show_scaffold" in _scaffolding_codes(text)
    # Dead id alone would miss — live path must use show_scaffold.
    assert "spoken_scaffolding" not in spoken_structure_hits(text)


def test_required_orientation_not_omitted_on_scaffold() -> None:
    """S2: required scaffolding is left untouched (no body rewrite / no omit)."""
    row = {
        "line_id": "vo_preface_episode_orientation",
        "required": True,
        "episode_orientation": True,
        "line_category": "episode_preface",
        "text": "Welcome back — in today's episode we unpack the trial design.",
    }
    fixed, changed = _strip_scaffolding(row)
    assert changed is False
    assert fixed is row or fixed.get("text") == row["text"]
    assert not fixed.get("omit")
    assert not fixed.get("skipped_optional")
    # Still active → sanitize refuse path can see scaffolding_active.
    assert _scaffolding_codes(str(fixed.get("text") or ""))


def test_required_scaffold_sanitize_refuses_without_rewrite(ctx) -> None:
    """S2: sanitize refuses scaffolding_active; does not rewrite text."""
    text = "Welcome back — in today's episode we unpack the trial design."
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_episode_orientation",
                "required": True,
                "episode_orientation": True,
                "line_category": "episode_preface",
                "text": text,
                "targets_segment_id": "seg_001",
                "placement": "before",
                "delivery": "synthesize",
                "gap_type": "orientation",
            }
        ],
        "gaps": [],
    }
    result = sanitize_gap_report(ctx, gap)
    assert not result.ok
    assert any("scaffolding_active" in e for e in result.errors)
    assert not any(a.get("action") == "rewrite_scaffolding" for a in result.actions)
    kept = (result.doc.get("interviewer_lines") or [None])[0]
    assert isinstance(kept, dict)
    assert kept.get("text") == text


def test_optional_line_may_omit_on_scaffold() -> None:
    row = {
        "line_id": "vo_optional_bridge",
        "required": False,
        "text": "Welcome back — in today's episode we unpack the trial design.",
    }
    fixed, changed = _strip_scaffolding(row)
    assert changed is True
    assert fixed.get("omit") is True
    assert fixed.get("skipped_optional") is True
    assert fixed.get("skip_reason") == "sanitize_scaffolding"


def test_ensure_orientation_refuses_remaining_scaffold(ctx, monkeypatch) -> None:
    from interview_mux.opening_orientation import ensure_episode_orientation

    # Keep scaffold text through earlier repair attempts so the refuse gate fires.
    monkeypatch.setattr(
        "interview_mux.spoken_copy_guard.spoken_copy_violations",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_prior_context.cold_open_layup_ok",
        lambda *a, **k: True,
    )
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_episode_orientation",
                "episode_orientation": True,
                "line_category": "episode_preface",
                "text": (
                    "Welcome back — in today's episode we unpack molecular "
                    "profiling stakes for listeners."
                ),
                "targets_segment_id": "seg_001",
                "placement": "before",
                "delivery": "synthesize",
                "orientation_missions": [
                    "guest_identity",
                    "conversation_topic",
                    "listener_stakes",
                ],
            }
        ]
    }
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "gap_framing_enabled": True,
        },
        skip_handoff=True,
    )
    with pytest.raises(RuntimeError, match="spoken scaffolding remains"):
        ensure_episode_orientation(ctx, gap, ["seg_001"])
