"""Two artifacts written without authority, now on the commit path.

`segments/boundaries.json` under `ideal_cuts_materialize` and
`understanding/interviewer_script.txt` both reached disk without ever asking
`write_permitted`. The first answered `not_allow:owner=edl_overlap_repair`, the
second `unknown_path` — so with `fail_closed()` on, one was a latent
`authority_denied:persist` and the other could be neither declared as a stage
output nor honestly ignored.

Each test here pins one half: the write is now permitted *through the gated
path*, and the paths that must stay refused still are.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux import artifact_ownership as ownership
from interview_mux.artifact_ownership import AuthorityDenied
from interview_mux.ideal_cuts import (
    BOUNDARIES_REL,
    boundaries_from_snapped_cuts,
    retract_own_boundaries,
)
from interview_mux.gap_framing import INTERVIEWER_SCRIPT_REL, commit_interviewer_script
from interview_mux.episode_structure import (
    COMPACT_DIGEST_PATH,
    commit_episode_structure_compact,
)

from run_fixtures import init_run_meta_for_test, isolated_run_ctx


@pytest.fixture(autouse=True)
def _fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both defects are invisible with the catalog fail-open."""
    monkeypatch.setenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", "1")
    assert ownership.fail_closed() is True


def _ctx(tmp_path: Path, run_id: str):
    ctx = isolated_run_ctx(tmp_path, run_id)
    init_run_meta_for_test(ctx)
    return ctx


def _snapped() -> dict:
    return {
        "cuts": [
            {"start_ms": 0, "end_ms": 60_000, "cut_id": "cut_001", "speaker_id": "spk_0"},
            {"start_ms": 61_000, "end_ms": 120_000, "cut_id": "cut_002", "speaker_id": "spk_1"},
        ],
        "snap_warnings": [],
    }


# ---------------------------------------------------------------------------
# Defect 1 — ideal_cuts_materialize publishes the segment contract
# ---------------------------------------------------------------------------

def test_materialize_may_publish_boundaries():
    """`bind_mode=both` (the default) makes materialize publish the contract."""
    ok, reason = ownership.write_permitted(None, BOUNDARIES_REL, "ideal_cuts_materialize")
    assert (ok, reason) == (True, "owner_rerun")


def test_edl_overlap_repair_is_still_the_authoritative_rewriter():
    """A new co-producer must not steal the last-writer seat or the heal pin."""
    row = ownership.row_for_path(BOUNDARIES_REL)
    assert row is not None
    assert row.authoritative == "edl_overlap_repair"
    assert row.heal_pin == "edl_overlap_repair"
    # boundary_detection stays first: it is the full-tape resume when a bind is
    # demoted, and ship_reachability reports producers[0] as the resume stage.
    assert row.producers[0] == "boundary_detection"
    assert row.producers[-1] == "edl_overlap_repair"
    assert "chapter_close_hitch" in row.producers
    assert row.producers.index("chapter_close_hitch") not in (0, len(row.producers) - 1)


def test_chapter_close_hitch_may_write_boundaries():
    """Hitch remints the contract after remap; fail-closed used to answer not_allow."""
    ok, reason = ownership.write_permitted(None, BOUNDARIES_REL, "chapter_close_hitch")
    assert (ok, reason) == (True, "owner_rerun")


def test_a_stage_with_no_claim_on_boundaries_is_still_refused():
    for stage in ("edl", "mix", "transitions"):
        ok, reason = ownership.write_permitted(None, BOUNDARIES_REL, stage)
        assert (ok, reason) == (False, "not_allow:owner=edl_overlap_repair"), stage


def test_materialize_boundaries_write_commits(tmp_path: Path):
    """The write that used to raise `authority_denied` now lands on disk."""
    ctx = _ctx(tmp_path, "exec_bind_ok")
    doc = boundaries_from_snapped_cuts(_snapped())
    ctx.write_json(BOUNDARIES_REL, doc, stage_key="ideal_cuts_materialize")
    assert ctx.artifact_exists(BOUNDARIES_REL)
    written = ctx.read_json(BOUNDARIES_REL)
    assert written["_meta"]["segment_contract"]["publisher_stage"] == "ideal_cuts_materialize"


def test_retract_drops_only_its_own_publication(tmp_path: Path):
    ctx = _ctx(tmp_path, "exec_retract_own")
    ctx.write_json(
        BOUNDARIES_REL,
        boundaries_from_snapped_cuts(_snapped()),
        stage_key="ideal_cuts_materialize",
    )
    assert retract_own_boundaries(ctx) is True
    assert not (ctx.run_dir / BOUNDARIES_REL).exists()


def test_retract_leaves_a_chapter_close_hitch_contract_alone(tmp_path: Path):
    """A raw `unlink` behind `boundaries_already_from_ideal_cuts` also deleted
    `chapter_close_hitch` publications — that contract belongs to that stage."""
    ctx = _ctx(tmp_path, "exec_retract_foreign")
    ctx.write_json(
        BOUNDARIES_REL,
        boundaries_from_snapped_cuts(_snapped(), publisher_stage="chapter_close_hitch"),
        stage_key="boundary_detection",
    )
    assert retract_own_boundaries(ctx) is False
    assert (ctx.run_dir / BOUNDARIES_REL).exists()


def test_retract_refuses_when_the_catalog_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Deleting a committed artifact is a mutation, so it asks the constitution.

    Pins the fix for the real hole: the old code `unlink`ed straight off
    `ctx.run_dir`, so no ownership answer could have stopped it.
    """
    ctx = _ctx(tmp_path, "exec_retract_denied")
    ctx.write_json(
        BOUNDARIES_REL,
        boundaries_from_snapped_cuts(_snapped()),
        stage_key="ideal_cuts_materialize",
    )

    def _deny(_ctx, path, stage_key, **_kw):
        return False, "not_allow:owner=edl_overlap_repair"

    monkeypatch.setattr(ownership, "write_permitted", _deny)
    with pytest.raises(AuthorityDenied) as exc:
        retract_own_boundaries(ctx)
    assert exc.value.verb == "invalidate"
    assert exc.value.path == BOUNDARIES_REL
    assert (ctx.run_dir / BOUNDARIES_REL).exists(), "refused retract must not delete"


# ---------------------------------------------------------------------------
# Defect 2 — understanding/interviewer_script.txt
# ---------------------------------------------------------------------------

def test_the_interviewer_script_has_an_ownership_row():
    row = ownership.row_for_path(INTERVIEWER_SCRIPT_REL)
    assert row is not None, "no catalog row — write_permitted answers unknown_path"
    assert row.producers == ("optimal_questions", "gap_framing_compose")
    assert row.authoritative == "gap_framing_compose"


@pytest.mark.parametrize(
    "stage", ["optimal_questions", "gap_framing_compose"]
)
def test_every_real_writer_of_the_script_is_permitted(stage: str):
    ok, reason = ownership.write_permitted(None, INTERVIEWER_SCRIPT_REL, stage)
    assert (ok, reason) == (True, "owner_rerun"), stage


def test_missing_framing_may_not_write_the_script():
    ok, reason = ownership.write_permitted(None, INTERVIEWER_SCRIPT_REL, "missing_framing")
    assert ok is False
    assert "not_allow" in reason


def test_a_foreign_stage_may_not_write_the_script():
    ok, reason = ownership.write_permitted(None, INTERVIEWER_SCRIPT_REL, "edl")
    assert (ok, reason) == (False, "not_allow:owner=gap_framing_compose")


def test_commit_interviewer_script_writes_through_the_gate(tmp_path: Path):
    ctx = _ctx(tmp_path, "exec_script_ok")
    commit_interviewer_script(ctx, "# script\n", stage_key="gap_framing_compose")
    assert ctx.read_path(INTERVIEWER_SCRIPT_REL).read_text(encoding="utf-8") == "# script\n"


def test_commit_interviewer_script_refuses_a_foreign_stage(tmp_path: Path):
    ctx = _ctx(tmp_path, "exec_script_denied")
    with pytest.raises(AuthorityDenied) as exc:
        commit_interviewer_script(ctx, "# script\n", stage_key="edl")
    assert exc.value.suggested_owner == "gap_framing_compose"
    assert not (ctx.run_dir / INTERVIEWER_SCRIPT_REL).exists()


def test_the_script_stages_and_flushes_like_any_owner_output(tmp_path: Path):
    """`Path.write_text` on `ctx.run_dir` skipped staging; `ctx.path` does not."""
    from interview_mux.write_staging import (
        enter_stage_staging,
        exit_stage_staging,
        flush_stage_writes,
        list_pending_paths,
    )

    ctx = _ctx(tmp_path, "exec_script_staged")
    enter_stage_staging("gap_framing_compose")
    try:
        commit_interviewer_script(ctx, "# staged\n", stage_key="gap_framing_compose")
        staged = ctx.run_dir / ".pending_writes" / "gap_framing_compose" / INTERVIEWER_SCRIPT_REL
        assert staged.is_file(), "write did not land in the stage's staging root"
        assert INTERVIEWER_SCRIPT_REL in list_pending_paths(ctx, "gap_framing_compose")
        assert not (ctx.run_dir / INTERVIEWER_SCRIPT_REL).exists()
    finally:
        exit_stage_staging()
    assert INTERVIEWER_SCRIPT_REL in flush_stage_writes(ctx, "gap_framing_compose")
    assert (ctx.run_dir / INTERVIEWER_SCRIPT_REL).read_text(encoding="utf-8") == "# staged\n"


def test_no_module_writes_the_script_with_raw_file_io():
    """Regression pin — the bypass was three ungated `Path.write_text` sites.

    Two named the path and wrote it on one line; the skip stub split the write
    across three, so the window has to be wider than a single line.
    """
    src = Path(__file__).resolve().parents[1] / "src" / "interview_mux"
    offenders: list[str] = []
    for path in sorted(src.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "interviewer_script.txt" not in line:
                continue
            window = "\n".join(lines[i : i + 4])
            if ".write_text(" in window or "open(" in window:
                offenders.append(f"{path.relative_to(src)}:{i + 1}")
    assert offenders == [], (
        "the interviewer script must go through commit_interviewer_script, "
        f"which asserts authority before staging: {offenders}"
    )


# ---------------------------------------------------------------------------
# Defect 3 — understanding/episode_structure_compact.txt
# ---------------------------------------------------------------------------

def test_the_episode_structure_compact_has_an_ownership_row():
    row = ownership.row_for_path(COMPACT_DIGEST_PATH)
    assert row is not None, "no catalog row — write_permitted answers unknown_path"
    assert row.producers == (
        "sound_design_plan",
        "chapter_close_hitch",
        "episode_structure_compose",
    )
    assert row.authoritative == "episode_structure_compose"


@pytest.mark.parametrize(
    "stage",
    ["episode_structure_compose", "sound_design_plan", "chapter_close_hitch"],
)
def test_every_real_writer_of_the_compact_is_permitted(stage: str):
    ok, reason = ownership.write_permitted(None, COMPACT_DIGEST_PATH, stage)
    assert (ok, reason) == (True, "owner_rerun"), stage


def test_a_foreign_stage_may_not_write_the_compact():
    ok, reason = ownership.write_permitted(None, COMPACT_DIGEST_PATH, "edl")
    assert (ok, reason) == (False, "not_allow:owner=episode_structure_compose")


def test_commit_episode_structure_compact_writes_through_the_gate(tmp_path: Path):
    ctx = _ctx(tmp_path, "exec_compact_ok")
    commit_episode_structure_compact(
        ctx, "compact digest\n", stage_key="episode_structure_compose"
    )
    assert (
        ctx.read_path(COMPACT_DIGEST_PATH).read_text(encoding="utf-8")
        == "compact digest\n"
    )


def test_commit_episode_structure_compact_refuses_a_foreign_stage(tmp_path: Path):
    ctx = _ctx(tmp_path, "exec_compact_denied")
    with pytest.raises(AuthorityDenied) as exc:
        commit_episode_structure_compact(ctx, "compact digest\n", stage_key="edl")
    assert exc.value.suggested_owner == "episode_structure_compose"
    assert not (ctx.run_dir / COMPACT_DIGEST_PATH).exists()


def test_the_compact_stages_and_flushes_like_any_owner_output(tmp_path: Path):
    """`Path.write_text` on `ctx.run_dir` skipped staging; `ctx.path` does not."""
    from interview_mux.write_staging import (
        enter_stage_staging,
        exit_stage_staging,
        flush_stage_writes,
        list_pending_paths,
    )

    ctx = _ctx(tmp_path, "exec_compact_staged")
    enter_stage_staging("episode_structure_compose")
    try:
        commit_episode_structure_compact(
            ctx, "# staged\n", stage_key="episode_structure_compose"
        )
        staged = (
            ctx.run_dir
            / ".pending_writes"
            / "episode_structure_compose"
            / COMPACT_DIGEST_PATH
        )
        assert staged.is_file(), "write did not land in the stage's staging root"
        assert COMPACT_DIGEST_PATH in list_pending_paths(ctx, "episode_structure_compose")
        assert not (ctx.run_dir / COMPACT_DIGEST_PATH).exists()
    finally:
        exit_stage_staging()
    assert COMPACT_DIGEST_PATH in flush_stage_writes(ctx, "episode_structure_compose")
    assert (ctx.run_dir / COMPACT_DIGEST_PATH).read_text(encoding="utf-8") == "# staged\n"


def test_no_module_writes_the_compact_with_raw_file_io():
    """Regression pin — persist_structure used an ungated Path.write_text."""
    src = Path(__file__).resolve().parents[1] / "src" / "interview_mux"
    offenders: list[str] = []
    for path in sorted(src.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "episode_structure_compact.txt" not in line:
                continue
            window = "\n".join(lines[i : i + 4])
            if ".write_text(" in window or "open(" in window:
                offenders.append(f"{path.relative_to(src)}:{i + 1}")
    assert offenders == [], (
        "the episode structure compact must go through "
        "commit_episode_structure_compact, which asserts authority before "
        f"staging: {offenders}"
    )
