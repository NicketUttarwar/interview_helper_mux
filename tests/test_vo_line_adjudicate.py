"""Tests for vo_line_adjudicate stage (Phase 3) and 5C delivery reorder."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.stages import vo_line_adjudicate as vo_line_adjudicate_stage
from interview_mux.v2.config import ALL_LLM_STAGES, DELIVERY_ORDER
from interview_mux.vo_line_adjudicate import (
    apply_adjudicate_results,
    line_adjudication_input_hash,
    lines_needing_adjudication,
    run_adjudicate_batches,
    run_intro_compose,
    score_layup_flow_fit,
)
from interview_mux.vo_synthesis_audit import nuke_all_synth_wavs_on_adjudicate_change
from run_fixtures import isolated_run_ctx, write_fixture_vo_wav


def _gap_with_body_line(**line_patch) -> dict:
    line = {
        "line_id": "vo_layup_seg_002",
        "gap_type": "nugget_layup",
        "text": "Before we hear how the buyer reacted, one detail sets up the pivot.",
        "targets_segment_id": "seg_002",
        "placement": "before",
        "delivery": "synthesize",
        "nugget_ids": ["nug_001"],
        "forward_unlock": "Why the snack pivot decided the price",
    }
    line.update(line_patch)
    return {"interviewer_lines": [line]}


def _corpus() -> dict:
    return {
        "nuggets": [
            {
                "nugget_id": "nug_001",
                "text_claim": "Snack insight",
                "evidence_quote": "as a snack",
                "salience": "high",
                "in_selection": False,
            },
            {
                "nugget_id": "nug_002",
                "text_claim": "Buyer pivot",
                "evidence_quote": "the buyer paused",
                "salience": "high",
                "in_selection": False,
            },
        ]
    }


def test_score_layup_flow_fit_rewards_bridge_not_restate():
    masks = {
        "natives": {
            "seg_002": {
                "comprehensible_text": "The buyer walked away from the deal after seeing the margin sheet.",
            }
        }
    }
    line = {
        "text": "One margin detail explains why the buyer hesitated before this clip.",
        "targets_segment_id": "seg_002",
        "forward_unlock": "Why the snack pivot decided the price",
    }
    target = masks["natives"]["seg_002"]["comprehensible_text"]
    score = score_layup_flow_fit(line, target, masks)
    assert score > 0.2


def test_lines_needing_adjudication_skips_unchanged_hash(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_hash")
    gap = _gap_with_body_line()
    plan = {
        "layups": [
            {
                "line_id": "vo_layup_seg_002",
                "target_segment_id": "seg_002",
                "forward_unlock": "Why the snack pivot decided the price",
            }
        ]
    }
    line = gap["interviewer_lines"][0]
    input_hash = line_adjudication_input_hash(line, plan["layups"][0])
    ctx.write_json(
        "understanding/vo_line_adjudication.json",
        {
            "lines": [
                {
                    "line_id": "vo_layup_seg_002",
                    "action": "air",
                    "input_hash": input_hash,
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json("understanding/native_comprehension_masks.json", {"natives": {}}, skip_handoff=True)
    need = lines_needing_adjudication(ctx, gap, plan, threshold=0.99)
    assert need == []


def test_apply_adjudicate_rewrite_is_advisory_only(tmp_path: Path) -> None:
    """S1: rewrite actions do not mutate gap body text or nuke WAVs."""
    from run_fixtures import mark_done_raw

    ctx = isolated_run_ctx(tmp_path, "adj_rewrite")
    ctx.write_json("run_meta.json", {"homunculus_version": "0.1.0"}, skip_handoff=True)
    gap = _gap_with_body_line()
    prior_text = gap["interviewer_lines"][0]["text"]
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    wav = ctx.path("vo_pickup/vo_layup_seg_002.wav")
    write_fixture_vo_wav(wav)
    mark_done_raw(ctx, "vo_synthesize")
    mark_done_raw(ctx, "edl_narrative_audit")

    updated, actions = apply_adjudicate_results(
        ctx,
        gap,
        [
            {
                "line_id": "vo_layup_seg_002",
                "action": "rewrite",
                "final_text": "Rewritten bridge into the buyer reaction.",
            }
        ],
    )
    assert actions[0]["action"] == "rewrite"
    assert updated["interviewer_lines"][0]["text"] == prior_text
    assert wav.is_file()
    assert ctx.is_done("vo_synthesize")
    assert ctx.is_done("edl_narrative_audit")


def test_run_adjudicate_batches_mockable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_batch")
    gap = _gap_with_body_line()
    captured: dict = {}

    def fake_runner(_ctx, _stage, _prompt, build_input, persist, **kwargs):
        captured["auto_complete"] = kwargs.get("auto_complete", True)
        payload = build_input(_ctx)
        artifacts = {
            "lines": [
                {
                    "line_id": payload["lines"][0]["line_id"],
                    "action": "air",
                    "input_hash": payload["lines"][0]["input_hash"],
                }
            ]
        }
        persist(_ctx, artifacts)
        return {"status": "complete", "artifacts": artifacts}

    rows = run_adjudicate_batches(
        ctx,
        ["vo_layup_seg_002"],
        gap,
        llm_runner=fake_runner,
    )
    assert rows and rows[0]["action"] == "air"
    assert ctx.artifact_exists("understanding/vo_line_adjudication.json")
    # Mid-batch mark_done is hollow — batches must defer completion (exec_13167).
    assert captured.get("auto_complete") is False
    assert not ctx.is_done("vo_line_adjudicate")


def test_run_adjudicate_batches_does_not_mark_done_mid_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): flow LLM must not hollow-stamp before seal.

    run_llm_stage_simple(auto_complete=True) marks done after each batch while
    adjudication.json is still missing → authority_denied:mark_done:hollow.
    """
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "adj_no_mid_done")
    gap = _gap_with_body_line()
    mark_calls: list[str] = []

    def fake_runner(c, stage, _prompt, build_input, persist, **kwargs):
        assert kwargs.get("auto_complete") is False
        payload = build_input(c)
        persist(
            c,
            {
                "lines": [
                    {
                        "line_id": payload["lines"][0]["line_id"],
                        "action": "air",
                        "final_text": payload["lines"][0].get("text") or "ok",
                        "input_hash": payload["lines"][0]["input_hash"],
                    }
                ]
            },
        )
        # Simulate what llm_simple would do if auto_complete stayed True.
        if kwargs.get("auto_complete", True):
            c.mark_done(stage)
            mark_calls.append(stage)
        return {"status": "complete"}

    run_adjudicate_batches(
        ctx,
        ["vo_layup_seg_002"],
        gap,
        llm_runner=fake_runner,
    )
    assert mark_calls == []
    assert ctx.artifact_exists("understanding/vo_line_adjudication.json")
    assert not ctx.is_done("vo_line_adjudicate")


def test_run_adjudicate_batches_coerces_null_final_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): LLM air+null final_text must still commit.

    OpenAI envelope allows null; artifact schema requires string. Without coerce,
    write_json raises → no adjudication → seed-order heal-spin vs vo_synthesize
    (exec_13163 vo_layup_seg_008).
    """
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "adj_null_ft")
    gap = _gap_with_body_line()
    spoken = gap["interviewer_lines"][0]["text"]
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)

    def fake_runner(_ctx, _stage, _prompt, build_input, persist):
        payload = build_input(_ctx)
        artifacts = {
            "lines": [
                {
                    "line_id": payload["lines"][0]["line_id"],
                    "action": "air",
                    "final_text": None,
                    "input_hash": payload["lines"][0]["input_hash"],
                }
            ]
        }
        persist(_ctx, artifacts)
        return {"status": "complete", "artifacts": artifacts}

    rows = run_adjudicate_batches(
        ctx,
        ["vo_layup_seg_002"],
        gap,
        llm_runner=fake_runner,
    )
    assert rows and rows[0]["action"] == "air"
    assert ctx.artifact_exists("understanding/vo_line_adjudication.json")
    doc = ctx.read_json("understanding/vo_line_adjudication.json")
    sealed = (doc.get("lines") or [])[0]
    assert isinstance(sealed.get("final_text"), str)
    assert sealed["final_text"] == spoken


def test_run_adjudicate_batches_coerces_null_sibling_leaves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade: null target_segment_id / rationale / disposition / nugget_ids seal."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "adj_null_sib")
    gap = _gap_with_body_line()
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)

    def fake_runner(_ctx, _stage, _prompt, build_input, persist):
        payload = build_input(_ctx)
        artifacts = {
            "lines": [
                {
                    "line_id": payload["lines"][0]["line_id"],
                    "action": "air",
                    "final_text": None,
                    "target_segment_id": None,
                    "flow_rationale": None,
                    "nugget_disposition": None,
                    "input_hash": None,
                    "nugget_ids": None,
                }
            ]
        }
        persist(_ctx, artifacts)
        return {"status": "complete", "artifacts": artifacts}

    rows = run_adjudicate_batches(
        ctx,
        ["vo_layup_seg_002"],
        gap,
        llm_runner=fake_runner,
    )
    assert rows and rows[0]["action"] == "air"
    doc = ctx.read_json("understanding/vo_line_adjudication.json")
    sealed = (doc.get("lines") or [])[0]
    assert isinstance(sealed["final_text"], str)
    assert isinstance(sealed["target_segment_id"], str)
    assert sealed["target_segment_id"] == "seg_002"
    assert sealed["flow_rationale"] == ""
    assert sealed["nugget_disposition"] == ""
    assert sealed["input_hash"] == ""
    assert sealed["nugget_ids"] == []


def test_intro_compose_mints_position_zero(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_intro")
    ctx.write_json("run_meta.json", {"homunculus_version": "0.1.0"}, skip_handoff=True)
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001", "seg_002"]}, skip_handoff=True)
    ctx.write_json("understanding/nugget_corpus.json", _corpus(), skip_handoff=True)
    gap = _gap_with_body_line()
    gap["_adjudicate_deferred_nuggets"] = ["nug_002"]

    def fake_intro(_ctx, _stage, _prompt, _build, persist):
        persist(
            _ctx,
            {
                "text": "Two forces collided before the first clip: snack economics and buyer nerve.",
                "nugget_ids": ["nug_002"],
                "intro_nugget_recovery": True,
            },
        )
        return {"status": "complete"}

    updated, intro_ids = run_intro_compose(ctx, gap, llm_runner=fake_intro)
    assert intro_ids
    lines = updated["interviewer_lines"]
    assert lines[0]["line_category"] == "episode_preface"
    assert lines[0].get("intro_nugget_recovery") is True
    assert ctx.artifact_exists("understanding/nugget_intro_compose.json")


def test_nugget_intro_compose_unwraps_stage_output_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): nested stage_output must seal flat text/nugget_ids.

    LLM returned {stage_output: {text, nugget_ids}} and persist wrote the wrapper
    → schema required-property fail (exec_13167).
    """
    from interview_mux.nugget_intro_compose import run_nugget_intro_compose

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "intro_unwrap")
    gap = _gap_with_body_line()
    ctx.write_json("understanding/nugget_corpus.json", _corpus(), skip_handoff=True)

    def fake_runner(_ctx, _stage, _prompt, _build, persist, **_kwargs):
        persist(
            _ctx,
            {
                "stage_output": {
                    "text": "What does it take to turn a promising cancer test into clinic use?",
                    "nugget_ids": ["nug_002"],
                    "clustered_themes": ["regulatory pathway"],
                    "rationale": "hook",
                },
                "_meta": {},
            },
        )
        return {"status": "complete"}

    out = run_nugget_intro_compose(
        ctx, gap, ["nug_002"], llm_runner=fake_runner
    )
    assert out.get("text")
    assert out.get("nugget_ids") == ["nug_002"]
    doc = ctx.read_json("understanding/nugget_intro_compose.json")
    assert "stage_output" not in doc
    assert isinstance(doc.get("text"), str) and doc["text"]
    assert doc.get("nugget_ids") == ["nug_002"]


def test_nugget_intro_reuses_sealed_on_limit_exhausted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MUX_FORENSICS=0: LimitExhausted after a sealed intro must not strand Part A."""
    from interview_mux.homunculus.budget import LimitExhausted
    from interview_mux.nugget_intro_compose import run_nugget_intro_compose

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "intro_reuse_cap")
    gap = _gap_with_body_line()
    ctx.write_json("understanding/nugget_corpus.json", _corpus(), skip_handoff=True)
    sealed = {
        "text": "Before a new cancer test can reach patients, the FDA path takes years.",
        "nugget_ids": ["nug_002"],
        "clustered_themes": ["regulatory pathway"],
        "rationale": "stake",
        "intro_nugget_recovery": True,
    }
    ctx.write_json(
        "understanding/nugget_intro_compose.json", sealed, skip_handoff=True
    )

    def boom_runner(*_a, **_k):
        raise LimitExhausted(
            "nugget_intro_compose",
            "max_invokes_per_identity",
            {"used": 3, "cap": 3},
        )

    out = run_nugget_intro_compose(ctx, gap, ["nug_002"], llm_runner=boom_runner)
    assert out.get("text") == sealed["text"]
    assert out.get("nugget_ids") == ["nug_002"]


def test_stage_skips_for_original_brain(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_skip")
    ctx.write_json("run_meta.json", {"homunculus_version": "0.0.0"}, skip_handoff=True)
    vo_line_adjudicate_stage.run_vo_line_adjudicate(ctx)
    # 0.0.0 skip now persists a schema stub so synth is not seed-blocked.
    assert ctx.artifact_exists("understanding/vo_line_adjudication.json")
    doc = ctx.read_json("understanding/vo_line_adjudication.json")
    assert str(doc.get("skip_reason") or "") == "homunculus_features_off"


def test_nuke_all_synth_wavs_on_adjudicate_change(tmp_path: Path) -> None:
    from run_fixtures import mark_done_raw

    ctx = isolated_run_ctx(tmp_path, "adj_nuke")
    ctx.write_json(
        "understanding/gap_report.json",
        _gap_with_body_line(),
        skip_handoff=True,
    )
    write_fixture_vo_wav(ctx.path("vo_pickup/vo_layup_seg_002.wav"))
    write_fixture_vo_wav(ctx.path("vo_pickup/tr_seg_001_seg_002.wav"))
    mark_done_raw(ctx, "vo_synthesize")
    removed = nuke_all_synth_wavs_on_adjudicate_change(ctx)
    assert removed >= 1
    assert not ctx.path("vo_pickup/vo_layup_seg_002.wav").is_file()
    # Transition bridges must survive adjudicate resynth (exec_11130).
    assert ctx.path("vo_pickup/tr_seg_001_seg_002.wav").is_file()
    assert not ctx.is_done("vo_synthesize")


def test_nuke_synth_wavs_selective_line_ids(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_nuke_selective")
    gap = _gap_with_body_line()
    gap["interviewer_lines"].append(
        {
            "line_id": "vo_layup_seg_009",
            "text": "Keep this wav.",
            "delivery": "synthesize",
            "targets_segment_id": "seg_009",
        }
    )
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    write_fixture_vo_wav(ctx.path("vo_pickup/vo_layup_seg_002.wav"))
    write_fixture_vo_wav(ctx.path("vo_pickup/vo_layup_seg_009.wav"))
    removed = nuke_all_synth_wavs_on_adjudicate_change(
        ctx, line_ids=["vo_layup_seg_002"]
    )
    assert removed >= 1
    assert not ctx.path("vo_pickup/vo_layup_seg_002.wav").is_file()
    assert ctx.path("vo_pickup/vo_layup_seg_009.wav").is_file()


def test_stage_peels_intro_and_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2/S3: stage must not mint intro or write allocation."""
    from interview_mux.vo_line_adjudicate import run_vo_line_adjudicate_stage

    ctx = isolated_run_ctx(tmp_path, "adj_peel")
    ctx.write_json("run_meta.json", {"homunculus_version": "0.2.0"}, skip_handoff=True)
    ctx.write_json(
        "understanding/gap_report.json",
        _gap_with_body_line(),
        skip_handoff=True,
    )
    ctx.write_json("understanding/nugget_corpus.json", _corpus(), skip_handoff=True)
    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.lines_needing_adjudication",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.evaluate_nugget_air_coverage",
        lambda *_a, **_k: {"ok": True, "errors": []},
    )
    intro_calls: list[str] = []

    def _boom_intro(*_a, **_k):
        intro_calls.append("called")
        raise AssertionError("intro must not run from stage")

    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.run_intro_compose", _boom_intro
    )
    run_vo_line_adjudicate_stage(ctx)
    assert intro_calls == []
    assert ctx.artifact_exists("understanding/vo_line_adjudication.json")
    assert not ctx.artifact_exists("understanding/nugget_allocation_plan.json")
    assert not ctx.artifact_exists("understanding/nugget_intro_compose.json")
    gap = ctx.read_json("understanding/gap_report.json")
    cats = [
        str(ln.get("line_category") or "")
        for ln in (gap.get("interviewer_lines") or [])
        if isinstance(ln, dict)
    ]
    assert "episode_preface" not in cats
    assert ctx.is_done("vo_line_adjudicate")


def test_adjudicate_fail_open_default_true() -> None:
    """VLA-B2: product default warn+continue on coverage shortfall."""
    from interview_mux.vo_line_adjudicate import adjudicate_cfg

    cfg = adjudicate_cfg({"analysis": {"gap_vo": {}}})
    assert cfg["adjudicate_fail_open"] is True


def test_adjudicate_coverage_fail_open_warns_not_loud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.vo_line_adjudicate import run_vo_line_adjudicate_stage

    ctx = isolated_run_ctx(tmp_path, "adj_fail_open")
    ctx.write_json("run_meta.json", {"homunculus_version": "0.2.0"}, skip_handoff=True)
    ctx.write_json(
        "understanding/gap_report.json",
        _gap_with_body_line(),
        skip_handoff=True,
    )
    ctx.write_json("understanding/nugget_corpus.json", _corpus(), skip_handoff=True)
    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.lines_needing_adjudication",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.collect_waived_nugget_ids",
        lambda *_a, **_k: set(),
    )
    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.evaluate_nugget_air_coverage",
        lambda *_a, **_k: {
            "ok": False,
            "nugget_air_coverage": 0.1,
            "errors": ["below_floor"],
            "min_nugget_air_coverage": 0.85,
        },
    )
    loud: list[str] = []

    def _loud(*_a, **_k):
        loud.append("raised")
        raise RuntimeError("loud_fail")

    monkeypatch.setattr("interview_mux.loud_fail.raise_loud_failure", _loud)
    warnings: list[str] = []

    def _log(msg: str, *a, level: str = "info", **k):
        if level == "warning":
            warnings.append(str(msg))

    monkeypatch.setattr(ctx, "log", _log)
    run_vo_line_adjudicate_stage(ctx)
    assert loud == []
    assert any("coverage below floor" in w.lower() for w in warnings)
    assert ctx.artifact_exists("understanding/vo_line_adjudication.json")
    assert ctx.is_done("vo_line_adjudicate")
    assert not ctx.artifact_exists("understanding/nugget_allocation_plan.json")


def test_adjudicate_incomprehensible_vo_hard_fails_even_fail_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q1A+: coverage may warn+continue; empty/junk synthesize VO always loud-fails."""
    from interview_mux.vo_line_adjudicate import (
        run_vo_line_adjudicate_stage,
        synthesize_vo_comprehensibility_errors,
    )

    bad = _gap_with_body_line(text="")
    assert synthesize_vo_comprehensibility_errors(bad)
    scaffold = _gap_with_body_line(text="Welcome back to today's episode about snacks.")
    assert synthesize_vo_comprehensibility_errors(scaffold)

    ctx = isolated_run_ctx(tmp_path, "adj_vo_hard")
    ctx.write_json("run_meta.json", {"homunculus_version": "0.2.0"}, skip_handoff=True)
    ctx.write_json("understanding/gap_report.json", bad, skip_handoff=True)
    ctx.write_json("understanding/nugget_corpus.json", _corpus(), skip_handoff=True)
    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.lines_needing_adjudication",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.collect_waived_nugget_ids",
        lambda *_a, **_k: set(),
    )
    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.evaluate_nugget_air_coverage",
        lambda *_a, **_k: {"ok": True, "errors": []},
    )
    loud_reasons: list[str] = []

    def _loud(ctx_arg, msg, *a, reason: str = "", **k):
        loud_reasons.append(str(reason or msg))
        raise RuntimeError("loud_fail")

    monkeypatch.setattr("interview_mux.loud_fail.raise_loud_failure", _loud)
    with pytest.raises(RuntimeError, match="loud_fail"):
        run_vo_line_adjudicate_stage(ctx)
    assert any("synthesize_vo_incomprehensible" in r for r in loud_reasons)


def test_scrub_spoken_edit_structure_clears_next_segment() -> None:
    from interview_mux.spoken_meta_lint import (
        scrub_spoken_edit_structure,
        spoken_structure_hits,
    )
    from interview_mux.vo_line_adjudicate import synthesize_vo_comprehensibility_errors

    raw = "What tensions carry over into the next segment?"
    cleaned = scrub_spoken_edit_structure(raw)
    assert "segment" not in cleaned.lower()
    assert not spoken_structure_hits(cleaned)
    report = {
        "interviewer_lines": [
            {
                "line_id": "vo_seed_seg_017",
                "text": cleaned,
                "delivery": "synthesize",
                "targets_segment_id": "seg_017",
            }
        ]
    }
    assert not synthesize_vo_comprehensibility_errors(report)


def test_scrub_spoken_gendered_pronoun_clears_intro_preface() -> None:
    """Cascade (MUX_FORENSICS=0): intro 'why he believes' must scrub for VO gate.

    exec_13167: synthesize_vo_comprehensibility_errors → spoken_gendered_pronoun
    on vo_intro_preface after intro compose.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.spoken_meta_lint import (
        scrub_spoken_edit_structure,
        spoken_structure_hits,
    )
    from interview_mux.vo_line_adjudicate import synthesize_vo_comprehensibility_errors

    raw = (
        "In this conversation, we explore why he believes combining "
        "circulating tumour-cell analysis could help."
    )
    assert "spoken_gendered_pronoun" in spoken_structure_hits(raw)
    cleaned = scrub_spoken_edit_structure(raw)
    assert "spoken_gendered_pronoun" not in spoken_structure_hits(cleaned)
    assert "they believe" in cleaned.lower()
    report = {
        "interviewer_lines": [
            {
                "line_id": "vo_intro_preface",
                "text": cleaned,
                "delivery": "synthesize",
                "targets_segment_id": "seg_001",
            }
        ]
    }
    assert not synthesize_vo_comprehensibility_errors(report)
