"""The solver has ZERO authority over what runs, and shadow mode does not change that.

Shadow logging is armed by DEFAULT (operator decision), so "inert" can no longer mean
"the run path never touches the solver": the walk consults it on every stage-selection
decision and appends one operator-tier log line per decision. The invariant the
promotion safety argument rests on is therefore narrower, and stated exactly.

**The solver cannot influence which stage runs while ``MUX_SOLVER_AUTHORITATIVE`` is
off.** These tests pin that from four directions:

1. **Selection is untouched** — the walk's chosen stage sequence is identical with the
   hook armed, silenced, and outright broken.
2. **Call sites are enumerated** — only the walk's two named seams, the capability
   predicate and the read-only API route may touch the solver, and the only one that
   can reorder stages is guarded by the authority switch.
3. **Evaluation is read-only** — evaluating the whole admissible set writes nothing;
   the decision log is the single file shadow mode adds, and it is append-only.
4. **Authority is off by default**, and the hook cannot raise into the walk.

``tests/test_solver_authoritative.py`` is the mirror image: the switch on.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from interview_mux import solver
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx

SRC = Path("src/interview_mux")
# Every module allowed to know the solver exists, and why:
#   solver.py             the module itself
#   web/server.py         read-only GUI/API read path (p2-observability)
#   homunculus/agenda.py  the shadow hook + the authoritative sequence
#   homunculus/runtime.py the LLM demotion when the solver is authoritative
ALLOWED_IMPORTERS: frozenset[str] = frozenset(
    {"solver.py", "web/server.py", "homunculus/agenda.py", "homunculus/runtime.py"}
)


def _ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "homunculus_control_plane": "deterministic",
            "run_mode": "full-auto",
            "full_auto": True,
        },
        skip_handoff=True,
    )
    return ctx


def _tree_fingerprint(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(str(path.relative_to(root)).encode("utf-8"))
        h.update(b":")
        h.update(hashlib.sha256(path.read_bytes()).digest())
        h.update(b"\n")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. stage selection is untouched
# ---------------------------------------------------------------------------

def _walk(
    tmp_path: Path, name: str, stages: list[str], monkeypatch, shadow: str | None
) -> list[str]:
    """Run the walk with dispatch stubbed, and report the stages it chose."""
    from interview_mux.homunculus import agenda

    if shadow is None:
        monkeypatch.delenv("MUX_SOLVER_SHADOW", raising=False)
    else:
        monkeypatch.setenv("MUX_SOLVER_SHADOW", shadow)
    ctx = _ctx(tmp_path, name)
    wav = ctx.final_path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 4096)
    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage", lambda c, s, **k: ran.append(s)
    )
    agenda.walk_seed_agenda(ctx, stages, reason="inert_test")
    return ran


def test_the_stage_sequence_is_identical_armed_silenced_and_broken(
    tmp_path: Path, monkeypatch
) -> None:
    """The one property that matters: shadow mode cannot move a stage."""
    monkeypatch.delenv("MUX_SOLVER_AUTHORITATIVE", raising=False)
    stages = ["transcribe", "speaker_roles", "utterance_segment"]

    armed = _walk(tmp_path, "inert_armed", stages, monkeypatch, None)
    silenced = _walk(tmp_path, "inert_silenced", stages, monkeypatch, "0")
    assert armed == silenced

    def _boom(*_a, **_k):
        raise RuntimeError("solver exploded")

    monkeypatch.setattr(solver, "compare_walk_choice", _boom)
    broken = _walk(tmp_path, "inert_broken", stages, monkeypatch, "1")
    assert broken == armed


def test_shadow_modes_whole_on_disk_footprint_is_the_decision_log(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "1")
    ctx = _ctx(tmp_path, "inert_footprint")

    def _files() -> set[str]:
        return {str(p.relative_to(ctx.run_dir)) for p in ctx.run_dir.rglob("*")}

    before = _files()
    solver.observe_walk_choice(ctx, "ingest", candidates=("ingest",))
    assert _files() - before <= {"operator", solver.SOLVER_DECISION_REL}


def test_the_decision_log_is_append_only(tmp_path: Path, monkeypatch) -> None:
    """Observation, not state: an earlier row is never rewritten."""
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "1")
    ctx = _ctx(tmp_path, "inert_append_only")
    solver.observe_walk_choice(ctx, "ingest", candidates=("ingest",))
    first = solver.read_decisions(ctx, limit=50)
    solver.observe_walk_choice(ctx, "transcribe", candidates=("transcribe",))
    second = solver.read_decisions(ctx, limit=50)
    assert second[: len(first)] == first
    assert len(second) == len(first) + 1


def test_only_the_enumerated_call_sites_import_the_solver() -> None:
    importers: set[str] = set()
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "interview_mux.solver" in text or "from interview_mux import solver" in text:
            importers.add(str(path.relative_to(SRC)))
    assert importers <= ALLOWED_IMPORTERS, sorted(importers - ALLOWED_IMPORTERS)


def test_every_run_path_import_of_the_solver_is_function_local() -> None:
    """Keeps the solver off the import graph, so a broken module cannot fail a boot."""
    for rel in sorted(ALLOWED_IMPORTERS - {"solver.py"}):
        for line in (SRC / rel).read_text(encoding="utf-8").splitlines():
            if "interview_mux.solver" not in line:
                continue
            assert line.startswith((" ", "\t")), f"{rel}: module-scope import — {line!r}"


def test_the_authority_switch_is_consulted_only_where_promotion_needs_it() -> None:
    callers = sorted(
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if "solver_authoritative" in p.read_text(encoding="utf-8")
    )
    assert callers == ["homunculus/agenda.py", "homunculus/runtime.py", "solver.py"]


def test_the_walk_reaches_the_solver_only_through_the_two_named_seams() -> None:
    """One shadow hook, one sequence hook — no incidental solver calls in the walk."""
    text = (SRC / "homunculus/agenda.py").read_text(encoding="utf-8")
    assert text.count("from interview_mux.solver import") == 2
    assert "observe_walk_choice" in text
    assert "authoritative_sequence" in text


def test_the_walk_never_branches_on_what_the_shadow_hook_returned() -> None:
    """Discarding the return value is what keeps an armed hook observation-only."""
    text = (SRC / "homunculus/agenda.py").read_text(encoding="utf-8")
    call = text.index("observe_walk_choice(\n")
    statement = text[text.rindex("\n", 0, call) + 1 : call]
    assert statement.strip() == "", f"return value bound to {statement.strip()!r}"


def test_the_walk_sequence_is_plain_seed_order_while_the_flag_is_off(
    tmp_path: Path, monkeypatch
) -> None:
    from interview_mux.homunculus.agenda import _walk_sequence

    monkeypatch.delenv("MUX_SOLVER_AUTHORITATIVE", raising=False)
    ctx = _ctx(tmp_path, "inert_sequence")
    stages = ["ingest", "transcribe", "speaker_roles"]
    assert list(_walk_sequence(ctx, stages, reason="test")) == stages


# ---------------------------------------------------------------------------
# 3. evaluation is read-only
# ---------------------------------------------------------------------------

def test_a_full_evaluation_leaves_the_run_directory_byte_identical(
    tmp_path: Path,
) -> None:
    """The decision functions themselves are pure — only the log writer writes."""
    ctx = _ctx(tmp_path, "inert_readonly")
    wav = ctx.final_path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 4096)

    before = _tree_fingerprint(ctx.run_dir)
    decision = solver.next_stage(ctx)
    solver.halt_payload(decision)
    solver.admissible_set(ctx, posture=solver.MANUAL)
    solver.admissible_set(ctx, posture=solver.PARTIAL)
    for sid in solver.dispatchable_stages():
        solver.evaluate_stage(ctx, sid)
    assert _tree_fingerprint(ctx.run_dir) == before


def test_decision_and_dispatch_stay_separate_functions() -> None:
    """§8.3 — the pure half must expose no way to act."""
    source = (SRC / "solver.py").read_text(encoding="utf-8")
    for forbidden in ("dispatch_stage", "run_stage", "mark_done", "take_gate_advance_lease"):
        assert forbidden not in source
    assert not hasattr(solver, "dispatch")


def test_evaluation_is_deterministic_for_the_same_disk_state(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "inert_deterministic")
    first = solver.admissible_set(ctx)
    second = solver.admissible_set(ctx)
    assert first.admissible == second.admissible
    assert first.exclusions() == second.exclusions()


# ---------------------------------------------------------------------------
# 4. authority off by default; the hook cannot raise
# ---------------------------------------------------------------------------

def test_authority_is_off_by_default_and_shadow_is_armed(monkeypatch) -> None:
    """The asymmetry is the operator's decision: collect evidence, decide nothing."""
    monkeypatch.delenv("MUX_SOLVER_AUTHORITATIVE", raising=False)
    monkeypatch.delenv("MUX_SOLVER_SHADOW", raising=False)
    assert solver.solver_authoritative() is False
    assert solver.shadow_logging_enabled() is True


def test_the_shadow_default_is_the_only_one_that_ships_on() -> None:
    """A promotion switch that could default on from a stray edit is the risk here."""
    source = (SRC / "solver.py").read_text(encoding="utf-8")
    assert '_env_on("MUX_SOLVER_AUTHORITATIVE", default=False)' in source
    assert '_env_on("MUX_SOLVER_SHADOW", default=True)' in source


def test_the_operator_can_silence_shadow_logging_entirely(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "0")
    ctx = _ctx(tmp_path, "inert_shadow_off")
    before = _tree_fingerprint(ctx.run_dir)
    solver.shadow_observe(ctx)
    assert solver.observe_walk_choice(ctx, "ingest", source="test") is None
    assert _tree_fingerprint(ctx.run_dir) == before
    assert solver.shadow_summary(ctx)["observations"] == 0


def test_the_shadow_hook_swallows_a_solver_bug_instead_of_breaking_the_walk(
    tmp_path: Path, monkeypatch
) -> None:
    """Armed by default, so a telemetry hook that can raise is one that loses a tape."""
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "1")
    ctx = _ctx(tmp_path, "inert_shadow_raises")

    def _boom(*_a, **_k):
        raise RuntimeError("solver exploded")

    # A broken writer must not raise either — the observation is simply lost.
    monkeypatch.setattr(solver, "_append_row", _boom)
    assert solver.observe_walk_choice(ctx, "ingest", source="test") is not None

    for attr in ("evaluate_stage", "posture_for", "lease_permits_acting"):
        monkeypatch.setattr(solver, attr, _boom)
    assert solver.observe_walk_choice(ctx, "ingest", source="test") is None


def test_the_dispatch_door_does_not_know_the_solver_exists() -> None:
    """The door refuses or allows on its own terms; the solver composes with it."""
    door = (SRC / "dispatch_door.py").read_text(encoding="utf-8")
    assert "solver" not in door
