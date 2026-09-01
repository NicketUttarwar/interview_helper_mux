from __future__ import annotations

from interview_mux.tone_taxonomy import validate_format_class, validate_tone_class


def test_validate_tone_class_maps_human_interest_aliases() -> None:
    assert validate_tone_class("human_interest") == "human_interest"
    assert validate_tone_class("human interest") == "human_interest"
    assert validate_tone_class("human-interest") == "human_interest"
    assert validate_tone_class("intimate") == "human_interest"
    assert validate_tone_class("warm") == "human_interest"


def test_validate_format_class_maps_legacy_tutorial() -> None:
    assert validate_format_class("tutorial") == "technical_deep_dive"
    assert validate_format_class("one_on_one") == "one_on_one"


def test_hyphen_boundary_keeps_ingest_out_of_vo_ingest() -> None:
    """Mirror parse_failed_stage token boundaries (do not import the e2e driver)."""
    low = (
        "required high-severity setup lines have no evidenced vo-ingest "
        "or nle placement before edl."
    )
    cand = "ingest"
    idx = low.find(cand)
    assert idx > 0
    before = low[idx - 1]
    after = low[idx + len(cand)]
    # Same rule as tools/full_auto_driver.parse_failed_stage
    is_token = (not before.isalnum() and before not in "_-") and (
        not after.isalnum() and after not in "_-"
    )
    assert is_token is False
    assert "vo-ingest" in low
    assert "edl" in low


def test_parse_failed_stage_prefers_llm_stage_over_needs_rerun() -> None:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    import full_auto_driver

    job = {
        "stage": "topic_coverage_audit",
        "message": (
            "LLM stage topic_coverage_audit incomplete: status=needs_input "
            "needs=[{'stage': 'segment_classification', 'type': 'rerun_stage'}]"
        ),
    }
    assert full_auto_driver.parse_failed_stage(job) == "topic_coverage_audit"


def test_parse_failed_stage_maps_g1_vo_open_sentinel() -> None:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    import full_auto_driver

    job = {
        "stage": "vo_synthesize",
        "error": "Unknown from_stage: g1_vo_open",
        "message": "Unknown from_stage: g1_vo_open",
    }
    assert full_auto_driver.parse_failed_stage(job) == "vo_line_adjudicate"


def test_parse_failed_stage_stale_transitions_not_invalidator() -> None:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    import full_auto_driver

    job = {
        "stage": "sound_design_plan",
        "error": (
            "master/transitions.json is marked stale "
            "(invalidated_by:nugget_layup_compose)"
        ),
        "message": "master/transitions.json is marked stale",
    }
    assert full_auto_driver.parse_failed_stage(job) == "transitions"
