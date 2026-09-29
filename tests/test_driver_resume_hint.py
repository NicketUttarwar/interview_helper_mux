"""The traversal driver reads the resume stage a failure names."""

from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "stub_pipeline_smoke", Path(__file__).resolve().parents[1] / "tools" / "stub_pipeline_smoke.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_resume_hint_reads_both_spellings() -> None:
    assert mod.resume_hint("Delivery incomplete after conductor — remaining stages: mix; resume=mix") == "mix"
    assert mod.resume_hint("junction_snip_qa remaster owed — resume mix: music_epoch_pre_beds_seat") == "mix"
    assert mod.resume_hint("no hint here") is None


def test_resume_hint_reads_seed_order_prerequisite() -> None:
    err = "RuntimeError: seed order: complete nugget_layup_compose before running refinement_agenda"
    assert mod.resume_hint(err) == "nugget_layup_compose"
    assert mod.resume_hint("something unrelated") is None


def test_resume_hint_reads_a_stage_refusal_naming_its_remedy() -> None:
    err = "incomplete_cut_unresolved: Mix refused: live residuals on_a_roll — recut/fuse/omit at junction_snip_qa first"
    assert mod.resume_hint(err) == "junction_snip_qa"
