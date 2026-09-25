"""Permanent AST/census lint — Land Honesty fences must not rot.

MUX_FORENSICS=0. Helpers live in ``tools/land_honesty_census_lint.py``
(source-text preferred; light AST for raw_stamp_session literals).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

_REPO = Path(__file__).resolve().parents[1]
_TOOLS = _REPO / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import land_honesty_census_lint as lh  # noqa: E402
from interview_mux.done_authority import (  # noqa: E402
    LAYUP_AUTHORITY_STAGES,
    RAW_STAMP_ALLOW,
    SHARED_PATH_PRODUCER_STAGES,
)


def test_writer_no_stage_done_touch_outside_run_context() -> None:
    """Sole Path.touch of ``.stage_done`` must stay inside RunContext.mark_done."""
    offenders = lh.find_stage_done_touch_outside_run_context()
    assert offenders == [], offenders


def test_writer_raw_stamp_allow_reasons() -> None:
    """RAW_STAMP_ALLOW is the closed set; call-site literals must be members."""
    assert "heal_or_refuse_mark" in RAW_STAMP_ALLOW
    assert "post_master_backfill" in RAW_STAMP_ALLOW
    assert "test_fixture" in RAW_STAMP_ALLOW
    # Production reasons only — test_fixture is tests/run_fixtures, not src.
    for reason in lh.raw_stamp_session_literal_reasons():
        assert reason in RAW_STAMP_ALLOW, reason


def test_writer_promote_uses_unpaid_land_blocks_promote() -> None:
    text = (lh.SRC_ROOT / "delivery_guardrails.py").read_text(encoding="utf-8")
    idx = text.index("def promote_complete_orphan_stage_done")
    window = text[idx : idx + 2800]
    assert "unpaid_land_blocks_promote" in window
    # Dig #2: reconcile_orphan must call promote (no parallel promote bypass).
    ridx = text.index("def reconcile_orphan_artifacts")
    rwindow = text[ridx : ridx + 1200]
    assert "promote_complete_orphan_stage_done" in rwindow


def test_writer_restamp_uses_honest_restamp() -> None:
    text = (lh.SRC_ROOT / "delivery_invariants.py").read_text(encoding="utf-8")
    idx = text.index("def apply_seed_order_heal")
    window = text[idx : idx + 2000]
    assert "honest_restamp" in window
    assert "Path.touch" not in window or "never" in window.lower()


def test_writer_census_families_in_code_and_md() -> None:
    src_blob = "\n".join(p.read_text(encoding="utf-8") for p in lh.iter_src_py())
    for label, needle in lh.WRITER_FAMILY_NEEDLES:
        assert needle in src_blob, f"writer family {label}: missing {needle}"


def test_writer_hollow_done_guard_documented_in_census() -> None:
    """Runtime hollow escalate is detection (not a stamp writer) but must stay listed."""
    assert (lh.SRC_ROOT / "hollow_done_guard.py").is_file()
    text = (lh.SRC_ROOT / "hollow_done_guard.py").read_text(encoding="utf-8")
    assert "land_honest" in text
    assert "escalate_hollow_done" in text


def test_advance_pipeline_skip_loops_no_bare_is_done() -> None:
    hits = lh.pipeline_bare_is_done_skip_hits()
    assert hits == [], f"bare is_done in pipeline skip path: {hits}"
    text = (lh.SRC_ROOT / "pipeline.py").read_text(encoding="utf-8")
    assert text.count("may_skip_as_complete") >= 4
    assert "land_honest" in text


def test_advance_must_honest_modules() -> None:
    for rel in sorted(lh.ADVANCE_MUST_HONEST):
        text = (lh.SRC_ROOT / rel).read_text(encoding="utf-8")
        ok = any(
            n in text
            for n in ("may_skip_as_complete", "land_honest", "may_clear_wait")
        )
        assert ok, f"{rel} must use land honesty advance APIs"


def test_advance_detection_only_allowlist_documented() -> None:
    for rel in ("homunculus/agenda.py", "hollow_done_guard.py"):
        assert rel in lh.DETECTION_ONLY or rel.split("/")[-1] in " ".join(
            lh.DETECTION_ONLY
        )
        assert (lh.SRC_ROOT / rel).is_file()


def test_advance_no_new_bare_is_done_skip_outside_allowlist() -> None:
    offenders = lh.advance_skip_wait_offenders()
    assert offenders == [], (
        "new bare is_done skip/wait site — use may_skip_as_complete/"
        f"land_honest/may_clear_wait or add DETECTION_ONLY: {offenders}"
    )


def test_unpaid_land_four_family_substrings() -> None:
    text = (lh.SRC_ROOT / "done_authority.py").read_text(encoding="utf-8")
    idx = text.index("def unpaid_land_reason")
    # Function body only (until next top-level def)
    end = text.find("\ndef ", idx + 1)
    body = text[idx:end]
    for needle in lh.UNPAID_FAMILY_SUBSTRINGS:
        assert needle in body, needle


def test_shared_path_and_layup_tables_in_code_and_census() -> None:
    assert SHARED_PATH_PRODUCER_STAGES
    assert LAYUP_AUTHORITY_STAGES
    text = (lh.SRC_ROOT / "done_authority.py").read_text(encoding="utf-8")
    assert "SHARED_PATH_PRODUCER_STAGES" in text
    assert "LAYUP_AUTHORITY_STAGES" in text
    census = lh.read_census()
    assert "SHARED_PATH_PRODUCER_STAGES" in census
    assert "LAYUP_AUTHORITY_STAGES" in census


def test_r6_disk_mapped_hollow_param_cardinality() -> None:
    """len(param) == len(ANALYSIS∪DELIVERY ∩ STAGE_ARTIFACT_DISK_PATHS − GATE)."""
    expected = lh.disk_mapped_hollow_stages()
    # Import the live param list from the matrix module (same construction).
    from test_land_honesty_disk_mapped_hollow import _DISK_MAPPED_HOLLOW_STAGES

    assert len(_DISK_MAPPED_HOLLOW_STAGES) == len(expected)
    assert set(_DISK_MAPPED_HOLLOW_STAGES) == set(expected)
    assert len(expected) >= 70
