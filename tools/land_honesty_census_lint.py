"""Land Honesty census lint helpers — writer / advance / unpaid permanence.

Source-text + light AST guards (prefer clear comments over brittle AST).
Used by ``tests/test_land_honesty_census_permanence.py``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "interview_mux"
CENSUS_MD = (
    REPO_ROOT
    / ".cursor"
    / "heal-clinic"
    / "classes"
    / "hollow_pass"
    / "done_constitution_census.md"
)

# Unpaid-land reason family substrings that must remain in unpaid_land_reason.
UNPAID_FAMILY_SUBSTRINGS: tuple[str, ...] = (
    "remaster owed",
    "music_epoch_pre_beds_seat",
    "speech_first_remaster_owed",
    "remutate unpaid",
    "stamp-alone",
    "shared-path",
)

# Intentional bare ``is_done`` for detection / GUI / hollow inverse — not skip/wait.
# New skip/wait sites must use may_skip_as_complete / land_honest / may_clear_wait
# instead of growing this list casually.
DETECTION_ONLY: frozenset[str] = frozenset(
    {
        "homunculus/agenda.py",  # remaining / hollow-missing detection
        "homunculus/runtime.py",  # seed-walk detection before heal
        "hollow_done_guard.py",  # scan: done ∧ ¬land_honest
        "delivery_guardrails.py",  # hollow snapshot / promote inverse
        "mix_junction_seat.py",  # demote hollow mix
        "defect_ledger.py",  # iterate stamped stages for close
        "llm_flow_hardening.py",  # orphan-promote candidate filter
        "stage_order_migration.py",  # migrate past already-output stages
        "thrash_hardening.py",  # hollow / promote scan filters
        "vo_synthesis_audit.py",  # cascade invalidate only if stamped
        "web/server.py",  # GUI stage_done status
        "web/runner.py",
        "web/job_progress.py",
        "web/session_routes.py",
        "gates.py",  # operator gate views
        "operator_gate_view.py",
        "journey_state.py",
        "gui_job_reconcile.py",
        "execution_report.py",
        "stage_guidance.py",
        "stage_steps.py",
        "run_context.py",  # is_done definition + mark path
    }
)

# Modules that must remain land-honest for advance / skip / wait.
ADVANCE_MUST_HONEST: frozenset[str] = frozenset(
    {
        "pipeline.py",
        "execution_status.py",
        "done_authority.py",
        "stages/gaps.py",  # gap_compose_stage_done
    }
)

# Writer-census families that must remain wired (see done_constitution_census.md).
WRITER_FAMILY_NEEDLES: tuple[tuple[str, str], ...] = (
    ("Normal stamp", "def mark_done"),
    ("try_mark_done", "def try_mark_done"),
    ("heal_or_refuse_mark", "def heal_or_refuse_mark"),
    ("honest_restamp", "def honest_restamp"),
    ("may_post_master_backfill", "def may_post_master_backfill"),
    ("promote_complete_orphan", "def promote_complete_orphan_stage_done"),
)


def iter_src_py() -> list[Path]:
    return sorted(p for p in SRC_ROOT.rglob("*.py") if p.is_file())


def read_census() -> str:
    return CENSUS_MD.read_text(encoding="utf-8")


def disk_mapped_hollow_stages() -> list[str]:
    from interview_mux.done_authority import GATE_MARKER_ONLY
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    return [
        sid
        for sid in list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
        if sid in STAGE_ARTIFACT_DISK_PATHS and sid not in GATE_MARKER_ONLY
    ]


def find_stage_done_touch_outside_run_context() -> list[str]:
    """Return relative paths that appear to Path.touch a ``.stage_done`` marker.

    Source-text proximity (not full dataflow): ``.stage_done`` within ~200 chars
    before a ``.touch(`` call, or ``marker.touch(`` outside run_context.
    """
    offenders: list[str] = []
    for path in iter_src_py():
        rel = str(path.relative_to(SRC_ROOT))
        if rel == "run_context.py":
            continue
        text = path.read_text(encoding="utf-8")
        if ".touch(" not in text:
            continue
        if "marker.touch(" in text and ".stage_done" in text:
            offenders.append(f"{rel}: marker.touch with .stage_done in file")
            continue
        # Proximity: stage_done … touch on same or nearby lines
        for m in re.finditer(r".stage_done.{0,200}?\.touch\(", text, re.DOTALL):
            offenders.append(f"{rel}: {m.group(0)[:80]!r}…")
    return offenders


def raw_stamp_session_literal_reasons() -> list[str]:
    """String literal reasons passed to ``raw_stamp_session`` under src/."""
    reasons: list[str] = []
    for path in iter_src_py():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name != "raw_stamp_session":
                continue
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                val = node.args[1].value
                if isinstance(val, str):
                    reasons.append(val)
            for kw in node.keywords:
                if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                    val = kw.value.value
                    if isinstance(val, str):
                        reasons.append(val)
    return reasons


def pipeline_bare_is_done_skip_hits() -> list[str]:
    """Bare ``is_done`` used as skip/continue in pipeline.py (must stay empty)."""
    text = (SRC_ROOT / "pipeline.py").read_text(encoding="utf-8")
    hits: list[str] = []
    # Skip-planning loops must not gate on bare is_done.
    for i, line in enumerate(text.splitlines(), start=1):
        if "is_done" not in line:
            continue
        # Comments / docstrings mentioning is_done are ok.
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        hits.append(f"pipeline.py:{i}: {line.strip()}")
    return hits


def advance_skip_wait_offenders() -> list[str]:
    """Files that look like skip-as-complete on bare ``is_done`` without honesty APIs.

    Source-text heuristic (narrow on purpose — pipeline.py is the hard fence):
    positive ``if … is_done(…): continue`` (not ``if not is_done``), or explicit
    "skip as complete" / "already complete" phrasing near ``is_done``.
    DETECTION_ONLY and ADVANCE_MUST_HONEST (checked separately) are excluded.
    """
    honesty = ("may_skip_as_complete", "land_honest", "may_clear_wait")
    # Positive done→continue only. ``if not is_done: continue`` is detection iteration.
    risk = re.compile(
        r"if\s+(?!not\b)[^\n]{0,60}?\bis_done\([^\n]{0,100}\)"
        r"[^\n]{0,80}:\s*(?:\n[^\n]{0,60})?\bcontinue\b|"
        r"(?:skip\s+as\s+complete|already\s+complete|skip\s+re-?invoke)"
        r"[^\n]{0,100}is_done\(|"
        r"is_done\([^\n]{0,100}"
        r"(?:skip\s+as\s+complete|already\s+complete|skip\s+re-?invoke)",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for path in iter_src_py():
        rel = str(path.relative_to(SRC_ROOT))
        if rel in DETECTION_ONLY or rel in ADVANCE_MUST_HONEST:
            continue
        text = path.read_text(encoding="utf-8")
        if "is_done(" not in text:
            continue
        if any(h in text for h in honesty):
            continue
        if risk.search(text):
            offenders.append(rel)
    return offenders
