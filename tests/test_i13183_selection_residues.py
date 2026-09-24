"""exec_13183 selection residues — CTA schema normalize + letter-start repair-once."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.artifact_sanitize.selection import (
    _inherit_letter_family_starts,
    _starts_unavailable_error,
    sanitize_master_selection,
)
from interview_mux.heal_routing import classify_heal_error
from interview_mux.media_ip_cta import normalize_media_ip_cta_rows
from interview_mux.prompt_validation import validate_master_selection
from run_fixtures import init_run_meta_for_test, isolated_run_ctx

FIXTURE = Path(__file__).parent / "fixtures" / "exec_13183_selection_residues"


def test_fixture_package_complete() -> None:
    assert (FIXTURE / "forensics_excerpt.json").is_file()
    assert (FIXTURE / "selection_cta_refuse.json").is_file()
    assert (FIXTURE / "letter_kids_starts.json").is_file()
    excerpt = json.loads((FIXTURE / "forensics_excerpt.json").read_text(encoding="utf-8"))
    assert "segment_starts_unavailable" in excerpt["fingerprints"][0]
    assert "clearly_media_ip_pitch" in excerpt["fingerprints"][1]


def test_normalize_cta_admits_schema(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "cta_norm")
    init_run_meta_for_test(ctx)
    bad = json.loads((FIXTURE / "selection_cta_refuse.json").read_text(encoding="utf-8"))
    # Raw shape fails schema (missing pitch + illegal extras).
    raw_errs = validate_master_selection(bad)
    assert raw_errs, raw_errs
    fixed = normalize_media_ip_cta_rows(bad)
    for row in fixed["media_ip_cta"]:
        assert "clearly_media_ip_pitch" in row
        assert "action" not in row
        assert "reason" not in row
    errs = validate_master_selection(fixed)
    assert errs == [], errs


def test_letter_kids_inherit_and_persist_hints(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "letter_starts")
    init_run_meta_for_test(ctx)
    doc = json.loads((FIXTURE / "letter_kids_starts.json").read_text(encoding="utf-8"))
    parent = doc["parent_spans"]["seg_062"]
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_062",
                    "start_ms": parent["start_ms"],
                    "end_ms": parent["end_ms"],
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "Parent span for letter-kid inherit.",
                }
            ]
        },
    )
    selection = {"ordered_segment_ids": list(doc["ordered_segment_ids"])}
    result = sanitize_master_selection(ctx, selection)
    assert result.ok, result.errors
    meta = (result.doc.get("_meta") or {})
    hints = meta.get("inherited_segment_spans") or {}
    assert "seg_062la" in hints
    assert "seg_062lb" in hints
    # Persist on disk → second sanitize must not refuse starts.
    ctx.write_json("master/selection.json", result.doc)
    result2 = sanitize_master_selection(ctx, result.doc)
    assert result2.ok, result2.errors
    assert not any("segment_starts_unavailable" in e for e in (result2.errors or []))


def test_starts_unavailable_without_parent_still_refuses() -> None:
    starts: dict[str, tuple[int, int]] = {}
    ordered = ["seg_062la", "seg_062lb"]
    err = _starts_unavailable_error(ordered, starts)
    assert err == "segment_starts_unavailable"
    # Inherit alone cannot invent spans with empty map.
    resolved = _inherit_letter_family_starts(starts, ordered)
    assert "seg_062la" not in resolved


def test_selection_commit_refused_fingerprint_pins_producer(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "sel_pin")
    init_run_meta_for_test(ctx)
    excerpt = json.loads((FIXTURE / "forensics_excerpt.json").read_text(encoding="utf-8"))
    fp = excerpt["fingerprints"][1]
    route = classify_heal_error(fp, ctx, stage="mix")
    assert route is not None
    assert route.from_stage == "nugget_layup_compose"
    assert "selection_commit" in route.family or "selection" in route.family
