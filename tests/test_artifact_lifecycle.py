from __future__ import annotations

from interview_mux.artifact_lifecycle import (
    LifecyclePhase,
    fingerprint_artifact,
    run_phase_checks,
    split_artifact_lists,
)


class _Ctx:
    def __init__(self) -> None:
        self.files: dict[str, dict] = {}

    def artifact_exists(self, rel: str) -> bool:
        return rel in self.files

    def read_json(self, rel: str):
        return self.files[rel]

    def write_json(self, rel: str, data, **kwargs):
        self.files[rel] = data

    def mutate_run_meta(self, fn):
        meta = self.files.setdefault("run_meta.json", {})
        fn(meta)


def test_fingerprint_adds_meta():
    art = fingerprint_artifact({"thesis": "hello world"}, "content_context")
    assert art["_meta"]["producer_stage"] == "content_context"
    assert art["_meta"]["content_hash"]


def test_split_artifact_lists_pending(monkeypatch):
    ctx = _Ctx()
    monkeypatch.setattr(
        "interview_mux.artifact_lifecycle._artifact_lifecycle_phase",
        lambda c, rel, stage_id: "pending",
    )
    committed, staged, lifecycle = split_artifact_lists(
        ctx, "content_context", ["understanding/content_brief.json"]
    )
    assert lifecycle["understanding/content_brief.json"] == "pending"
    assert not committed


def test_run_phase_checks_pre_call_schema():
    errors = run_phase_checks(_Ctx(), "content_context", LifecyclePhase.PRE_CALL)
    assert isinstance(errors, list)


def test_stamp_stale_skips_upstream_producer_file():
    from interview_mux.artifact_lifecycle import stamp_stale_and_archive
    from interview_mux.run_context import RunContext

    ctx = RunContext(create=True)
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Precision oncology from circulating tumour cells.",
            "topics": [{"name": "liquid biopsy", "summary": "blood draw diagnostics"}],
            "_meta": {"producer_stage": "content_context", "stale": False},
        },
        skip_handoff=True,
    )
    stamped = stamp_stale_and_archive(ctx, "ideal_cuts_propose")
    doc = ctx.read_json("understanding/content_brief.json")
    assert not (doc.get("_meta") or {}).get("stale")
    assert "understanding/content_brief.json" not in stamped


def test_read_stale_guard_allows_producer_rewrite():
    from interview_mux.artifact_lifecycle import read_stale_guard

    ctx = _Ctx()
    ctx.files["understanding/content_brief.json"] = {
        "thesis": "hello world thesis text",
        "_meta": {"stale": True, "stale_reason": "invalidated_by:ideal_cuts_propose"},
    }
    assert (
        read_stale_guard(
            ctx, "understanding/content_brief.json", consumer_stage="content_context"
        )
        is None
    )
