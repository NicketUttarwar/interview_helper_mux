"""Tests for prompt example-pack injection."""

from __future__ import annotations

from interview_mux.prompt_examples import append_examples_to_system, load_compact_examples, prompt_examples_enabled


def test_prompt_examples_disabled_returns_unchanged(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.prompt_examples.prompt_examples_enabled",
        lambda stage_key=None: False,
    )
    base = "System prompt body."
    assert append_examples_to_system(base, "speaker_roles") == base


def test_load_compact_examples_speaker_roles():
    if not prompt_examples_enabled("speaker_roles"):
        return
    text = load_compact_examples("speaker_roles")
    assert text is None or len(text) > 20
