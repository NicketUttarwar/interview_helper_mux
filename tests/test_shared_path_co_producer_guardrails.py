"""Co-producer shared-path guardrails (brief + boundaries).

MUX_FORENSICS=0.

Covers the safe package + residuals:
1) Soft lint — no new bare literal writes; write_json guard wired
2) Commit helper / write_json choke-point meta merge / sacred protect
3) Cascade handoff contracts
4) Residuals — producer_claim_ok, intentional stale preserve, write_json(rel)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ["MUX_FORENSICS"] = "0"

_REPO = Path(__file__).resolve().parents[1]
_TOOLS = _REPO / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import shared_path_co_producer_lint as spl  # noqa: E402
from interview_mux.artifact_writes import write_validated_artifact  # noqa: E402
from interview_mux.run_context import RunContext  # noqa: E402
from interview_mux.shared_path_commit import (  # noqa: E402
    BOUNDARIES_REL,
    CONTENT_BRIEF_REL,
    commit_boundaries_doc,
    commit_content_brief_doc,
    merge_shared_path_meta,
    persist_allow_stages,
    producer_claim_ok,
    protect_sacred_fields,
)
from run_fixtures import isolated_run_ctx, minimal_content_brief  # noqa: E402


@pytest.fixture
def ctx(tmp_path, monkeypatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "shared_path_guard")
    c._one_writer_raw = True
    return c


def test_soft_lint_no_new_bare_shared_writes() -> None:
    offenders = spl.find_bare_shared_path_writes()
    assert offenders == [], (
        "new bare write_json to content_brief/boundaries — use "
        f"commit_*_doc or write_validated_artifact, or review baseline: {offenders}"
    )


def test_write_json_guard_remains_wired() -> None:
    assert spl.write_json_guard_wired() is True


def test_allow_vs_a05_drift_is_documented() -> None:
    """ALLOW is wider than A-05 peers by design — keep the note non-empty or empty."""
    notes = spl.find_allow_vs_a05_drift()
    assert isinstance(notes, list)
    assert any("segments/boundaries.json" in n for n in notes)


def test_producer_claim_ok_accepts_allow_co_producers() -> None:
    assert producer_claim_ok(BOUNDARIES_REL, "boundary_detection")
    assert producer_claim_ok(BOUNDARIES_REL, "chapter_close_hitch")
    assert producer_claim_ok(BOUNDARIES_REL, "ideal_cuts_materialize")
    assert not producer_claim_ok(BOUNDARIES_REL, "full_master_ranking")
    assert producer_claim_ok(CONTENT_BRIEF_REL, "content_brief_reanchor")
    assert not producer_claim_ok(CONTENT_BRIEF_REL, "")


def test_merge_meta_preserves_producer_when_not_claiming() -> None:
    disk = {
        "thesis": "Keep me",
        "_meta": {"producer_stage": "content_context", "stale": True, "stale_reason": "x"},
    }
    incoming = {"thesis": "Keep me", "host_name": "Ada", "_meta": {}}
    out = merge_shared_path_meta(
        incoming, disk=disk, stage_key=None, claim_producer=False, clear_stale=True
    )
    assert out["_meta"]["producer_stage"] == "content_context"
    assert "stale" not in out["_meta"]


def test_merge_meta_claims_when_stage_provided() -> None:
    disk = {"_meta": {"producer_stage": "content_context"}}
    incoming = {"thesis": "T", "_meta": {}}
    out = merge_shared_path_meta(
        incoming,
        disk=disk,
        stage_key="content_brief_reanchor",
        claim_producer=True,
    )
    assert out["_meta"]["producer_stage"] == "content_brief_reanchor"


def test_protect_sacred_restores_empty_thesis() -> None:
    disk = {"thesis": "Original thesis", "topics": [{"name": "A", "summary": "s"}]}
    incoming = {"thesis": "", "topics": []}
    out = protect_sacred_fields(incoming, disk=disk, rel=CONTENT_BRIEF_REL)
    assert out["thesis"] == "Original thesis"
    assert out["topics"] == disk["topics"]


def test_commit_content_brief_preserves_meta_on_name_patch(ctx: RunContext) -> None:
    ctx.write_json(
        CONTENT_BRIEF_REL,
        {
            **minimal_content_brief(thesis="Stable thesis"),
            "_meta": {"producer_stage": "content_context"},
        },
        skip_handoff=True,
    )
    brief = ctx.read_json(CONTENT_BRIEF_REL)
    brief["host_name"] = "Patched Host"
    brief["_meta"] = {}  # wipe attempt
    commit_content_brief_doc(ctx, brief, claim_producer=False, protect_sacred=True)
    disk = ctx.read_json(CONTENT_BRIEF_REL)
    assert disk["host_name"] == "Patched Host"
    assert disk["thesis"] == "Stable thesis"
    assert (disk.get("_meta") or {}).get("producer_stage") == "content_context"


def test_write_json_rel_variable_preserves_producer(ctx: RunContext) -> None:
    """Residual: write_json(rel) still goes through the choke-point guard."""
    ctx.write_json(
        CONTENT_BRIEF_REL,
        {
            **minimal_content_brief(thesis="Via rel"),
            "_meta": {"producer_stage": "content_context"},
        },
        skip_handoff=True,
    )
    rel = CONTENT_BRIEF_REL
    doc = ctx.read_json(rel)
    doc["host_name"] = "FromRel"
    doc["_meta"] = {}
    ctx.write_json(rel, doc, skip_handoff=True)  # no stage_key → no claim, protect sacred
    disk = ctx.read_json(CONTENT_BRIEF_REL)
    assert disk["host_name"] == "FromRel"
    assert disk["thesis"] == "Via rel"
    assert (disk.get("_meta") or {}).get("producer_stage") == "content_context"


def test_intentional_stale_stamp_preserved(ctx: RunContext) -> None:
    """Residual: lifecycle-style stale=True must not be cleared by the guard."""
    base = {
        **minimal_content_brief(thesis="Stale me"),
        "_meta": {"producer_stage": "content_context"},
    }
    ctx.write_json(CONTENT_BRIEF_REL, base, skip_handoff=True)
    stamped = ctx.read_json(CONTENT_BRIEF_REL)
    meta = dict(stamped.get("_meta") or {})
    meta["stale"] = True
    meta["stale_reason"] = "invalidated_by:boundary_detection"
    stamped["_meta"] = meta
    ctx.write_json(CONTENT_BRIEF_REL, stamped, skip_handoff=True)
    disk = ctx.read_json(CONTENT_BRIEF_REL)
    assert (disk.get("_meta") or {}).get("stale") is True
    assert (disk.get("_meta") or {}).get("producer_stage") == "content_context"


def test_handoff_reanchor_via_validated_write_keeps_thesis(ctx: RunContext) -> None:
    """Cascade: content_context → reanchor must not empty thesis on partial patch."""
    ctx.write_json(
        CONTENT_BRIEF_REL,
        {
            **minimal_content_brief(thesis="Pass-1 thesis"),
            "_meta": {"producer_stage": "content_context", "stale": True},
        },
        skip_handoff=True,
    )
    patch = {
        "topics": [
            {
                "name": "Topic A",
                "summary": "Summary.",
                "segment_ids": ["seg_001"],
            }
        ],
        "topic_relationships": [
            {
                "from_topic": "Topic A",
                "to_topic": "Topic A",
                "relation": "supports",
                "description": "self",
                "evidence_segment_ids": ["seg_001"],
            }
        ],
    }
    write_validated_artifact(
        ctx,
        CONTENT_BRIEF_REL,
        patch,
        merge_from_disk=True,
        stage_key="content_brief_reanchor",
    )
    disk = ctx.read_json(CONTENT_BRIEF_REL)
    assert disk.get("thesis") == "Pass-1 thesis"
    assert (disk.get("_meta") or {}).get("producer_stage") == "content_brief_reanchor"
    assert not (disk.get("_meta") or {}).get("stale")
    topics = [t for t in (disk.get("topics") or []) if isinstance(t, dict)]
    assert any((t.get("segment_ids") or []) == ["seg_001"] for t in topics)


def test_handoff_boundaries_resplit_keeps_rows(ctx: RunContext) -> None:
    """Cascade: detection land → resplit rewrite stays non-empty + claims stage."""
    ctx.write_json(
        "segments/boundaries.json",
        {
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "boundary_type": "topic",
                    "proposed_split_reason": "topic_shift",
                }
            ],
            "_meta": {"producer_stage": "boundary_detection"},
        },
        skip_handoff=True,
    )
    doc = ctx.read_json(BOUNDARIES_REL)
    rows = list(doc.get("boundaries") or [])
    rows.append(
        {
            "segment_id": "seg_002",
            "start_ms": 5000,
            "end_ms": 9000,
            "boundary_type": "topic",
            "proposed_split_reason": "topic_shift",
        }
    )
    commit_boundaries_doc(
        ctx,
        {**doc, "boundaries": rows, "_meta": {}},
        stage_key="boundary_topic_resplit",
        claim_producer=True,
        protect_sacred=True,
    )
    disk = ctx.read_json(BOUNDARIES_REL)
    assert len(disk.get("boundaries") or []) >= 2
    assert (disk.get("_meta") or {}).get("producer_stage") == "boundary_topic_resplit"


def test_empty_boundaries_wipe_restored_when_not_claiming(ctx: RunContext) -> None:
    """Residual: non-claim write cannot empty boundaries rows."""
    ctx.write_json(
        BOUNDARIES_REL,
        {
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "boundary_type": "topic",
                    "proposed_split_reason": "topic_shift",
                }
            ],
            "_meta": {"producer_stage": "boundary_detection"},
        },
        skip_handoff=True,
    )
    commit_boundaries_doc(
        ctx,
        {"boundaries": [], "_meta": {}},
        claim_producer=False,
        protect_sacred=True,
    )
    disk = ctx.read_json(BOUNDARIES_REL)
    assert len(disk.get("boundaries") or []) == 1
    assert (disk.get("_meta") or {}).get("producer_stage") == "boundary_detection"


def test_persist_allow_stages_covers_primary_producers() -> None:
    brief = persist_allow_stages(CONTENT_BRIEF_REL)
    bounds = persist_allow_stages(BOUNDARIES_REL)
    assert "content_context" in brief and "content_brief_reanchor" in brief
    assert "boundary_detection" in bounds and "boundary_topic_resplit" in bounds
