"""Soft census: bare writes to co-producer shared paths.

Runtime choke point is ``RunContext.write_json`` → ``guard_shared_path_on_write``
(covers ``write_json(rel)`` variables). This lint still fails on *new* literal
``write_json("…/content_brief|boundaries.json")`` that bypass review — prefer
``commit_*_doc`` for clarity.

Also asserts the write_json guard remains wired.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "interview_mux"

SHARED_RELS: frozenset[str] = frozenset(
    {
        "understanding/content_brief.json",
        "segments/boundaries.json",
    }
)

REL_CONST_HINTS: frozenset[str] = frozenset(
    {
        "BOUNDARIES_REL",
        "CONTENT_BRIEF_REL",
    }
)

SAFE_APIS: frozenset[str] = frozenset(
    {
        "commit_content_brief_doc",
        "commit_boundaries_doc",
        "write_validated_artifact",
        "make_stage_persist",
        "guard_shared_path_on_write",
        "prepare_shared_path_doc",
        "shared_path_write_opts",
    }
)

# Meta-only stale stamps may still call write_json directly; guard preserves stale.
KNOWN_RAW_BASELINE: frozenset[str] = frozenset(
    {
        "artifact_lifecycle.py",
        "shared_path_commit.py",
        "run_context.py",  # choke point itself
    }
)

_WRITE_CALL = re.compile(
    r"""(?P<api>write_json|write_committed_json)\s*\(\s*"""
    r"""(?:ctx\s*,\s*)?"""
    r"""(?P<arg>(?P<str>['"](?:understanding/content_brief\.json|segments/boundaries\.json)['"])"""
    r"""|(?P<const>BOUNDARIES_REL|CONTENT_BRIEF_REL))\b"""
)

_WRITE_JSON_REL = re.compile(
    r"""write_json\s*\(\s*rel\s*,"""
)


def iter_src_py() -> list[Path]:
    return sorted(p for p in SRC_ROOT.rglob("*.py") if p.is_file())


def _window(text: str, start: int, before: int = 80, after: int = 200) -> str:
    lo = max(0, start - before)
    hi = min(len(text), start + after)
    return text[lo:hi]


def write_json_guard_wired() -> bool:
    """True when RunContext.write_json still calls guard_shared_path_on_write."""
    text = (SRC_ROOT / "run_context.py").read_text(encoding="utf-8")
    return "guard_shared_path_on_write" in text and "SHARED_PATH_COMMIT_RELS" in text


def find_bare_shared_path_writes() -> list[str]:
    """Return offender strings for new literal bare writes."""
    offenders: list[str] = []
    for path in iter_src_py():
        file_rel = str(path.relative_to(SRC_ROOT)).replace("\\", "/")
        if file_rel in KNOWN_RAW_BASELINE:
            continue
        text = path.read_text(encoding="utf-8")
        for match in _WRITE_CALL.finditer(text):
            win = _window(text, match.start())
            if any(api in win for api in SAFE_APIS):
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            snippet = text.splitlines()[line_no - 1].strip()[:100]
            offenders.append(f"{file_rel}:{line_no}: {snippet}")
    return offenders


def find_write_json_rel_shared_mentions() -> list[str]:
    """Advisory: ``write_json(rel)`` in files that mention shared paths.

    Not a hard fail — runtime guard covers these. Listed so reviews stay aware.
    """
    notes: list[str] = []
    for path in iter_src_py():
        file_rel = str(path.relative_to(SRC_ROOT)).replace("\\", "/")
        if file_rel in KNOWN_RAW_BASELINE:
            continue
        text = path.read_text(encoding="utf-8")
        if not any(r in text for r in SHARED_RELS) and not any(
            c in text for c in REL_CONST_HINTS
        ):
            continue
        for match in _WRITE_JSON_REL.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            notes.append(f"{file_rel}:{line_no}")
    return notes


def find_allow_vs_a05_drift() -> list[str]:
    """Informational: ALLOW stages not in A-05 unmark peer set (not a hard fail)."""
    from interview_mux.artifact_ownership import ALLOW
    from interview_mux.post_decision_sanitize import SHARED_PATH_CO_PRODUCERS
    from interview_mux.shared_path_commit import SHARED_PATH_COMMIT_RELS

    notes: list[str] = []
    for path in sorted(SHARED_PATH_COMMIT_RELS):
        allow = {
            str(a.stage)
            for a in ALLOW
            if a.path == path and a.verb == "persist" and a.stage
        }
        peers = set(SHARED_PATH_CO_PRODUCERS.get(path) or ())
        extra = sorted(allow - peers)
        if extra:
            notes.append(
                f"{path}: ALLOW-only co-producers={extra} (A-05 peers={sorted(peers)})"
            )
    return notes


__all__ = [
    "KNOWN_RAW_BASELINE",
    "SAFE_APIS",
    "SHARED_RELS",
    "find_allow_vs_a05_drift",
    "find_bare_shared_path_writes",
    "find_write_json_rel_shared_mentions",
    "write_json_guard_wired",
]
