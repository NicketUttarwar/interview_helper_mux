"""A split's id remap lands under a key the ownership table accepts (ISSUES 129)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux import artifact_ownership as ao
from interview_mux import artifact_repairs as ar
from interview_mux import write_staging as ws
from run_fixtures import isolated_run_ctx

EVALS = "understanding/gap_evaluations.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "remap")
    yield c
    ws.exit_stage_staging()


def test_ranking_has_no_row_for_the_evaluations(ctx) -> None:
    ok, reason = ao.write_permitted(ctx, EVALS, "full_master_ranking", role="producer", verb="persist")
    assert not ok and ao.is_foreign_refusal(reason)
    assert ao.owner_of(EVALS) == "missing_framing"


def test_the_remap_presents_the_owner_and_lands(ctx, monkeypatch) -> None:
    writes: list[dict] = []

    def _write(rel, doc, **kw):
        writes.append({"rel": rel, **kw})
        dest = ctx.final_path(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(doc), encoding="utf-8")
        return dest

    monkeypatch.setattr(ctx, "write_json", _write)
    ws.enter_stage_staging("full_master_ranking")
    doc = {"evaluations": [{"segment_id": "seg_009a", "severity": "low"}]}
    assert ar.persist_segment_id_remap(ctx, EVALS, doc) is True
    assert writes == [
        {"rel": EVALS, "skip_handoff": True, "stage_key": "missing_framing", "mutation_class": "segment_id_remap"}
    ]


def test_a_stage_that_owns_the_document_writes_as_itself(ctx, monkeypatch) -> None:
    writes: list[dict] = []
    monkeypatch.setattr(ctx, "write_json", lambda rel, doc, **kw: writes.append({"rel": rel, **kw}))
    ws.enter_stage_staging("missing_framing")
    assert ar.persist_segment_id_remap(ctx, EVALS, {"evaluations": []}) is True
    assert writes == [{"rel": EVALS, "skip_handoff": True, "stage_key": "missing_framing"}]


def test_no_accepted_key_is_reported_not_raised(ctx, monkeypatch) -> None:
    monkeypatch.setattr(ao, "write_permitted", lambda *a, **k: (False, "deny:test"))
    called: list[str] = []
    monkeypatch.setattr(ctx, "write_json", lambda rel, doc, **kw: called.append(rel))
    ws.enter_stage_staging("full_master_ranking")
    assert ar.persist_segment_id_remap(ctx, EVALS, {"evaluations": []}) is False
    assert called == []


def test_the_split_propagation_uses_the_remap_writer_for_foreign_documents() -> None:
    src = Path(ar.__file__).read_text(encoding="utf-8")
    body = src[src.find("def propagate_nle_split_segment_refs(") :]
    body = body[: body.find("\ndef _normalize_audit_issue_row")]
    for rel in ("master/coverage_audit.json", "master/narrative_plan.json", "understanding/gap_evaluations.json"):
        assert f'persist_segment_id_remap(ctx, "{rel}"' in body
        assert f'ctx.write_json("{rel}"' not in body
